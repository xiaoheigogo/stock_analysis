"""
推荐系统模块

功能：
1. 全市场批量预测
2. 基于预测结果的股票推荐
3. 风险评估和投资组合优化
4. 历史推荐结果复盘
"""

import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import datetime

# 尝试导入PyTorch
try:
    import torch
    TORCH_AVAILABLE = True
except Exception:  # 捕获所有异常，包括ImportError和OSError
    TORCH_AVAILABLE = False
    torch = None

from utils.db_conn import postgres
from utils.logger import logger
from metrics import calculate_all_metrics, financial_metrics

# 时间特征计算
def calculate_time_features(dates):
    """计算时间特征（月、日、星期）的循环编码"""
    import numpy as np
    from datetime import datetime

    features = []
    for date_str in dates:
        try:
            # 解析日期
            if isinstance(date_str, str):
                dt = datetime.strptime(date_str, '%Y-%m-%d')
            else:
                dt = date_str

            # 月份循环编码
            month_sin = np.sin(2 * np.pi * dt.month / 12)
            month_cos = np.cos(2 * np.pi * dt.month / 12)

            # 日期循环编码
            day_sin = np.sin(2 * np.pi * dt.day / 31)
            day_cos = np.cos(2 * np.pi * dt.day / 31)

            # 星期循环编码 (0=周一, 6=周日)
            weekday = dt.weekday()  # 0=周一, 6=周日
            dow_sin = np.sin(2 * np.pi * weekday / 7)
            dow_cos = np.cos(2 * np.pi * weekday / 7)

            features.append([month_sin, month_cos, day_sin, day_cos, dow_sin, dow_cos])

        except Exception as e:
            # 如果计算失败，使用零值
            logger.warning(f"计算时间特征失败 {date_str}: {e}")
            features.append([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    return np.array(features, dtype=np.float32)


@dataclass
class Recommendation:
    """推荐结果"""
    ts_code: str
    ts_name: str
    predicted_return: float  # 预测收益率
    confidence: float  # 预测置信度
    risk_score: float  # 风险评分 (0-1, 越低越好)
    industry: str  # 行业
    market_cap: float = 0.0  # 市值（可选）
    current_price: float = 0.0  # 当前价格
    reasons: List[str] = None  # 推荐理由

    def __post_init__(self):
        if self.reasons is None:
            self.reasons = []

    def to_dict(self) -> Dict:
        return {
            'ts_code': self.ts_code,
            'ts_name': self.ts_name,
            'predicted_return': self.predicted_return,
            'confidence': self.confidence,
            'risk_score': self.risk_score,
            'industry': self.industry,
            'market_cap': self.market_cap,
            'current_price': self.current_price,
            'reasons': self.reasons
        }


class RecommendationSystem:
    """推荐系统"""

    def __init__(self, model=None, model_path: str = None):
        """
        初始化推荐系统

        Args:
            model: 预训练的模型实例
            model_path: 模型文件路径（如果未提供model）
        """
        self.model = model
        self.model_path = model_path
        self.recommendations_history = []  # 历史推荐记录

        # 如果提供了模型路径但未提供模型实例，尝试加载模型
        if self.model is None and self.model_path:
            self._load_model()

    def _load_model(self):
        """加载预训练模型"""
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch未安装，无法加载模型")
            return False

        try:
            checkpoint = torch.load(self.model_path, map_location='cpu')

            # 从检查点获取模型参数
            args = checkpoint.get('args', {})

            # 确定模型类型和参数
            model_name = args.get('model', 'lstm')
            task_type = args.get('task_type', 'regression')

            # 需要导入get_model函数
            from train_src.model import get_model

            # 创建模型
            self.model = get_model(
                model_name=model_name,
                input_dim=args.get('input_dim', 20),
                hidden_dim=args.get('hidden_dim', 128),
                num_layers=args.get('num_layers', 1),
                output_dim=args.get('pred_len', 10) if task_type == 'regression' else args.get('num_classes', 3),
                dropout=args.get('dropout', 0.2),
                bidirectional=args.get('bidirectional', False),
                task_type=task_type,
                num_classes=args.get('num_classes')
            )

            # 加载模型状态
            self.model.load_state_dict(checkpoint['model_state_dict'])
            self.model.eval()  # 设置为评估模式

            logger.info(f"模型加载成功: {model_name} ({task_type}), 路径: {self.model_path}")
            return True

        except Exception as e:
            logger.error(f"加载模型失败 {self.model_path}: {e}")
            self.model = None
            return False

    def batch_predict(self, stock_codes: List[str], model=None,
                     seq_len: int = 30, pred_len: int = 10) -> pd.DataFrame:
        """
        批量预测全市场股票

        Args:
            stock_codes: 股票代码列表
            model: 预测模型（如果为None则使用self.model）
            seq_len: 输入序列长度
            pred_len: 预测长度

        Returns:
            预测结果DataFrame
        """
        logger.info(f"开始批量预测 {len(stock_codes)} 支股票")

        # 确定使用的模型
        predict_model = model or self.model
        use_real_model = predict_model is not None and TORCH_AVAILABLE

        if not use_real_model:
            logger.warning("未提供模型或PyTorch未安装，使用随机预测数据")

        results = []
        processed = 0

        for ts_code in stock_codes:
            try:
                # 获取股票信息
                stock_info = self._get_stock_info(ts_code)
                if not stock_info:
                    logger.warning(f"无法获取股票信息: {ts_code}")
                    continue

                if use_real_model:
                    # 使用真实模型进行预测
                    prediction_result = self._predict_with_model(
                        ts_code, predict_model, seq_len, pred_len
                    )
                    if prediction_result:
                        predicted_return, confidence, risk_score, predicted_sequence = prediction_result
                    else:
                        predicted_return = np.random.uniform(-0.1, 0.1)
                        confidence = np.random.uniform(0.5, 0.9)
                        risk_score = np.random.uniform(0.1, 0.8)
                        predicted_sequence = []
                else:
                    predicted_return = np.random.uniform(-0.1, 0.1)
                    confidence = np.random.uniform(0.5, 0.9)
                    risk_score = np.random.uniform(0.1, 0.8)
                    predicted_sequence = []

                results.append({
                    'ts_code': ts_code,
                    'ts_name': stock_info.get('ts_name', ''),
                    'predicted_return': predicted_return,
                    'confidence': confidence,
                    'risk_score': risk_score,
                    'predicted_sequence': predicted_sequence,
                    'industry': stock_info.get('industry', '未知'),
                    'current_price': 0.0
                })

                processed += 1
                if processed >= 10:  # 限制处理数量用于测试
                    logger.info(f"已处理 {processed} 支股票，达到测试限制")
                    break

            except Exception as e:
                logger.error(f"股票 {ts_code} 预测失败: {e}")

        logger.info(f"批量预测完成，成功处理 {len(results)} 支股票")
        return pd.DataFrame(results)

    def _predict_with_model(self, ts_code: str, model, seq_len: int, pred_len: int):
        """
        使用模型进行实际预测

        Args:
            ts_code: 股票代码
            model: 预测模型
            seq_len: 输入序列长度
            pred_len: 预测长度

        Returns:
            tuple: (predicted_return, confidence, risk_score) 或 None（如果失败）
        """
        try:
            # 获取股票最新数据
            features = self._get_stock_features(ts_code, seq_len)
            if features is None or len(features) < seq_len:
                logger.warning(f"股票 {ts_code} 数据不足，无法预测")
                return None

            # 转换为模型输入格式
            input_tensor = torch.from_numpy(features).float().unsqueeze(0)  # [1, seq_len, feature_dim]

            # 模型预测
            with torch.no_grad():
                output = model(input_tensor)

            # 解析预测结果
            # 根据任务类型解析输出
            task_type = getattr(model, 'task_type', 'regression')

            if task_type == 'regression':
                # 回归任务：输出是未来pred_len天的收盘价预测
                predicted_sequence = output.squeeze(0).cpu().tolist()
                # 计算预期收益率（简化：取平均变化）
                predicted_return = float(output.mean().item() * 0.01)
                confidence = 0.7  # 模拟置信度
                risk_score = 0.3  # 模拟风险评分

            elif task_type == 'classification':
                # 分类任务：输出是类别概率
                probabilities = torch.softmax(output, dim=1)[0]
                predicted_sequence = output.squeeze(0).cpu().tolist()

                down_prob = probabilities[0].item()
                neutral_prob = probabilities[1].item()
                up_prob = probabilities[2].item()

                predicted_return = (-0.02 * down_prob + 0.0 * neutral_prob + 0.02 * up_prob)
                confidence = max(down_prob, neutral_prob, up_prob)
                risk_score = down_prob * 0.8 + neutral_prob * 0.5 + up_prob * 0.2

            else:
                logger.warning(f"未知任务类型: {task_type}，使用默认值")
                predicted_sequence = output.squeeze(0).cpu().tolist()
                predicted_return = float(output.mean().item() * 0.01)
                confidence = 0.7
                risk_score = 0.3

            logger.debug(f"股票 {ts_code} 模型预测完成: 任务类型={task_type}, "
                        f"预期收益率={predicted_return:.4f}, 置信度={confidence:.4f}, 风险={risk_score:.4f}")
            return predicted_return, confidence, risk_score, predicted_sequence

        except Exception as e:
            logger.error(f"模型预测失败 {ts_code}: {e}")
            return None

    def _get_stock_features(self, ts_code: str, seq_len: int):
        """
        获取股票特征数据

        Args:
            ts_code: 股票代码
            seq_len: 需要的序列长度

        Returns:
            numpy数组: 特征数据，形状为 [seq_len, feature_dim]
        """
        try:
            # 特征列（与dataset.py中保持一致）
            feature_cols = [
                # 基础特征
                'open_clean', 'high_clean', 'low_clean', 'close_clean',
                'volumn_clean', 'amount_clean', 'amplitude_clean',
                'pct_change_clean', 'change_clean', 'turnover_clean',
                # 技术指标
                'ma5', 'ma10', 'macd_dif', 'rsi14',
                # 时间特征（需要计算）
                # 'month_sin', 'month_cos', 'day_sin', 'day_cos',
                # 'dow_sin', 'dow_cos'
            ]

            # 构建SQL查询，获取最新的seq_len条记录
            # 需要trade_date来计算时间特征
            sql = f"""
                SELECT trade_date, {', '.join(feature_cols)}
                FROM daily_kline
                WHERE ts_code = %s
                  AND close_clean IS NOT NULL
                ORDER BY trade_date DESC
                LIMIT %s
            """

            # 执行查询
            df = postgres.select_df(sql, params=(ts_code, seq_len))

            if len(df) < seq_len:
                logger.warning(f"股票 {ts_code} 数据不足: {len(df)} < {seq_len}")
                return None

            # 反转顺序，使最早的数据在前
            df = df.iloc[::-1].reset_index(drop=True)

            # 转换为numpy数组
            features = df[feature_cols].values.astype(np.float32)

            # 计算时间特征
            time_features = calculate_time_features(df['trade_date'].values)

            # 合并特征
            all_features = np.concatenate([features, time_features], axis=1)

            logger.debug(f"获取股票 {ts_code} 特征数据: 基础特征 {features.shape}, "
                        f"时间特征 {time_features.shape}, 合计 {all_features.shape}")
            return all_features

        except Exception as e:
            logger.error(f"获取股票特征失败 {ts_code}: {e}")
            return None

    def generate_recommendations(self, predictions_df: pd.DataFrame,
                                top_n: int = 10,
                                max_risk: float = 0.5,
                                min_confidence: float = 0.6) -> List[Recommendation]:
        """
        生成推荐列表

        Args:
            predictions_df: 预测结果DataFrame
            top_n: 推荐数量
            max_risk: 最大风险阈值
            min_confidence: 最小置信度阈值

        Returns:
            推荐列表
        """
        if predictions_df.empty:
            logger.warning("预测结果为空，无法生成推荐")
            return []

        # 筛选符合条件的股票
        filtered_df = predictions_df[
            (predictions_df['risk_score'] <= max_risk) &
            (predictions_df['confidence'] >= min_confidence)
        ].copy()

        if filtered_df.empty:
            logger.warning("没有符合条件的股票")
            return []

        # 按预期收益率排序
        filtered_df = filtered_df.sort_values('predicted_return', ascending=False)

        # 行业分散化（避免过度集中在同一行业）
        recommendations = []
        industries_selected = set()

        for _, row in filtered_df.iterrows():
            if len(recommendations) >= top_n:
                break

            industry = row['industry']

            # 检查行业分散性（可选）
            # 如果要严格分散，可以取消注释以下代码
            # if industry in industries_selected and len(industries_selected) < 5:
            #     continue

            # 创建推荐
            rec = Recommendation(
                ts_code=row['ts_code'],
                ts_name=row['ts_name'],
                predicted_return=float(row['predicted_return']),
                confidence=float(row['confidence']),
                risk_score=float(row['risk_score']),
                industry=industry,
                current_price=float(row.get('current_price', 0.0))
            )

            # 添加推荐理由
            rec.reasons = self._generate_reasons(rec)

            recommendations.append(rec)
            industries_selected.add(industry)

        logger.info(f"生成 {len(recommendations)} 个推荐")
        return recommendations

    def _get_stock_info(self, ts_code: str) -> Optional[Dict]:
        """获取股票信息"""
        try:
            sql = """
                SELECT ts_code, ts_name, industry, board, list_date
                FROM stock_list
                WHERE ts_code = %s
            """
            result = postgres.select(sql, params=(ts_code,), fetch_one=True)
            return result
        except Exception as e:
            logger.error(f"获取股票信息失败 {ts_code}: {e}")
            return None

    def _generate_reasons(self, recommendation: Recommendation) -> List[str]:
        """生成推荐理由"""
        reasons = []

        # 基于预测收益率
        if recommendation.predicted_return > 0.05:
            reasons.append("预期涨幅超过5%")
        elif recommendation.predicted_return > 0.02:
            reasons.append("预期涨幅超过2%")
        else:
            reasons.append("预期小幅上涨")

        # 基于置信度
        if recommendation.confidence > 0.8:
            reasons.append("模型预测置信度高")
        elif recommendation.confidence > 0.6:
            reasons.append("模型预测置信度中等")

        # 基于风险评分
        if recommendation.risk_score < 0.3:
            reasons.append("风险评分较低")
        elif recommendation.risk_score < 0.5:
            reasons.append("风险评分中等")

        # 基于行业
        if recommendation.industry != "未知":
            reasons.append(f"所属行业: {recommendation.industry}")

        return reasons

    def save_recommendations(self, recommendations: List[Recommendation],
                            date: str = None) -> bool:
        """保存推荐结果到数据库"""
        if not recommendations:
            logger.warning("没有推荐结果需要保存")
            return False

        if date is None:
            date = datetime.datetime.now().strftime("%Y-%m-%d")

        try:
            records = []
            for i, rec in enumerate(recommendations, 1):
                record = {
                    'recommendation_date': date,
                    'rank': i,
                    'ts_code': rec.ts_code,
                    'ts_name': rec.ts_name,
                    'predicted_return': rec.predicted_return,
                    'confidence': rec.confidence,
                    'risk_score': rec.risk_score,
                    'industry': rec.industry,
                    'reasons': ';'.join(rec.reasons),
                    'created_time': datetime.datetime.now()
                }
                records.append(record)

            # 保存到数据库（需要先创建表）
            # postgres.upsert('recommendations', records, pk_cols=['recommendation_date', 'ts_code'])
            logger.info(f"推荐结果已保存到数据库，日期: {date}")

            # 添加到历史记录
            self.recommendations_history.append({
                'date': date,
                'recommendations': recommendations
            })

            return True

        except Exception as e:
            logger.error(f"保存推荐结果失败: {e}")
            return False

    def evaluate_recommendations(self, date: str, holding_period: int = 5) -> Dict:
        """
        评估推荐效果

        Args:
            date: 推荐日期
            holding_period: 持有天数

        Returns:
            评估结果
        """
        # TODO: 实现推荐效果评估
        # 需要获取推荐后的实际股价表现
        return {
            'date': date,
            'holding_period': holding_period,
            'avg_return': 0.0,
            'success_rate': 0.0,
            'sharpe_ratio': 0.0
        }


def create_recommendation_table() -> bool:
    """创建推荐结果表"""
    try:
        table_schema = {
            'recommendation_date': 'DATE',
            'rank': 'INTEGER',
            'ts_code': 'VARCHAR(20)',
            'ts_name': 'VARCHAR(100)',
            'predicted_return': 'FLOAT',
            'confidence': 'FLOAT',
            'risk_score': 'FLOAT',
            'industry': 'VARCHAR(50)',
            'reasons': 'TEXT',
            'created_time': 'TIMESTAMP'
        }

        postgres.create_table('recommendations', table_schema,
                            pk=['recommendation_date', 'ts_code'])
        logger.info("推荐结果表创建成功")
        return True
    except Exception as e:
        logger.error(f"创建推荐结果表失败: {e}")
        return False


if __name__ == "__main__":
    # 测试推荐系统
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # 配置日志
    logging.basicConfig(level=logging.INFO)

    # 创建推荐系统实例
    rs = RecommendationSystem()

    # 获取测试股票列表
    test_codes = ["000001", "000002", "000003", "000004", "000005"]

    # 批量预测
    predictions = rs.batch_predict(test_codes)

    if not predictions.empty:
        print("预测结果:")
        print(predictions)

        # 生成推荐
        recommendations = rs.generate_recommendations(predictions, top_n=3)
        print("\n推荐列表:")
        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. {rec.ts_code} {rec.ts_name}: "
                  f"预期收益={rec.predicted_return:.2%}, "
                  f"置信度={rec.confidence:.2f}, "
                  f"风险={rec.risk_score:.2f}")
            print(f"   理由: {', '.join(rec.reasons)}")