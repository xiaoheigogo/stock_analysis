"""
金融评估指标模块

包含回归和分类任务的评估指标，特别针对股票预测的金融指标。
"""

import numpy as np
# 尝试导入PyTorch
try:
    import torch
    TORCH_AVAILABLE = True
except Exception:  # 捕获所有异常，包括ImportError和OSError
    TORCH_AVAILABLE = False
    torch = None
import sklearn.metrics as sk_metrics
from typing import List, Dict, Tuple, Optional, Union, Any
import pandas as pd


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                      feature_scaler=None) -> Dict[str, float]:
    """
    回归任务评估指标

    Args:
        y_true: 真实值（归一化）
        y_pred: 预测值（归一化）
        feature_scaler: 特征缩放器，用于反归一化

    Returns:
        评估指标字典
    """
    metrics = {}

    # 基础回归指标（基于归一化值）
    metrics['mse'] = float(np.mean((y_true - y_pred) ** 2))
    metrics['mae'] = float(np.mean(np.abs(y_true - y_pred)))
    metrics['rmse'] = float(np.sqrt(metrics['mse']))

    # R²分数
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    metrics['r2'] = float(1 - ss_res / ss_tot) if ss_tot != 0 else 0.0

    # 如果提供了缩放器，计算原始尺度上的指标
    if feature_scaler is not None:
        try:
            # 假设y是收盘价，我们需要反归一化
            # 这里简化处理：假设我们只能反归一化单特征
            # 实际应用中需要更精细的处理
            pass
        except:
            pass

    return metrics


def classification_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                          y_prob: Optional[np.ndarray] = None) -> Dict[str, float]:
    """
    分类任务评估指标

    Args:
        y_true: 真实类别标签
        y_pred: 预测类别标签
        y_prob: 预测概率（对于多分类）

    Returns:
        评估指标字典
    """
    metrics = {}

    # 基础分类指标
    metrics['accuracy'] = float(sk_metrics.accuracy_score(y_true, y_pred))
    metrics['precision'] = float(sk_metrics.precision_score(y_true, y_pred, average='weighted', zero_division=0))
    metrics['recall'] = float(sk_metrics.recall_score(y_true, y_pred, average='weighted', zero_division=0))
    metrics['f1'] = float(sk_metrics.f1_score(y_true, y_pred, average='weighted', zero_division=0))

    # 多分类的混淆矩阵（简化）
    try:
        cm = sk_metrics.confusion_matrix(y_true, y_pred)
        # 计算每个类别的准确率
        class_accuracies = cm.diagonal() / cm.sum(axis=1)
        metrics['class_accuracy_mean'] = float(np.mean(class_accuracies[~np.isnan(class_accuracies)]))
        metrics['class_accuracy_std'] = float(np.std(class_accuracies[~np.isnan(class_accuracies)]))
    except:
        pass

    # 如果提供了概率，计算AUC等
    if y_prob is not None:
        try:
            # 对于二分类
            if y_prob.shape[1] == 2:
                metrics['auc'] = float(sk_metrics.roc_auc_score(y_true, y_prob[:, 1]))
            # 对于多分类，计算每类的AUC并平均
            elif y_prob.shape[1] > 2:
                # 将y_true转换为one-hot编码
                y_true_onehot = np.eye(y_prob.shape[1])[y_true]
                metrics['auc'] = float(sk_metrics.roc_auc_score(y_true_onehot, y_prob, average='macro', multi_class='ovr'))
        except:
            pass

    return metrics


def financial_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                     initial_price: float = 100.0) -> Dict[str, float]:
    """
    金融专用评估指标

    Args:
        y_true: 真实涨跌幅序列（百分比，如0.01表示1%）
        y_pred: 预测涨跌幅序列
        initial_price: 初始价格（用于计算策略收益）

    Returns:
        金融指标字典
    """
    metrics = {}

    if len(y_true) == 0 or len(y_pred) == 0:
        return metrics

    # 确保是numpy数组
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)

    # 1. 方向准确率（预测涨跌方向是否正确）
    direction_true = np.sign(y_true)  # 1:上涨，0:持平，-1:下跌
    direction_pred = np.sign(y_pred)
    direction_correct = (direction_true == direction_pred)
    metrics['direction_accuracy'] = float(np.mean(direction_correct))

    # 2. 预测与实际的相关性
    if len(y_true) > 1:
        try:
            correlation = np.corrcoef(y_true, y_pred)[0, 1]
            metrics['correlation'] = float(correlation if not np.isnan(correlation) else 0.0)
        except:
            metrics['correlation'] = 0.0

    # 3. 基于预测的简单交易策略回测
    try:
        # 简单策略：预测上涨则买入并持有到下一天，预测下跌则卖出/空仓
        positions = np.where(y_pred > 0, 1, 0)  # 1:持有，0:空仓
        # 计算策略收益（忽略交易成本）
        strategy_returns = positions * y_true
        # 计算基准收益（一直持有）
        benchmark_returns = y_true

        # 累计收益
        strategy_cum_return = np.prod(1 + strategy_returns) - 1
        benchmark_cum_return = np.prod(1 + benchmark_returns) - 1

        metrics['strategy_return'] = float(strategy_cum_return)
        metrics['benchmark_return'] = float(benchmark_cum_return)
        metrics['excess_return'] = float(strategy_cum_return - benchmark_cum_return)

        # 夏普比率（简化，假设无风险利率为0）
        if len(strategy_returns) > 1:
            sharpe_ratio = np.mean(strategy_returns) / np.std(strategy_returns) * np.sqrt(252)  # 年化
            metrics['sharpe_ratio'] = float(sharpe_ratio if not np.isnan(sharpe_ratio) else 0.0)

        # 最大回撤
        cumulative_returns = np.cumprod(1 + strategy_returns)
        peak = np.maximum.accumulate(cumulative_returns)
        drawdown = (peak - cumulative_returns) / peak
        metrics['max_drawdown'] = float(np.max(drawdown) if len(drawdown) > 0 else 0.0)

        # 胜率（盈利交易比例）
        winning_trades = strategy_returns > 0
        total_trades = positions.sum()
        metrics['win_rate'] = float(winning_trades.sum() / total_trades if total_trades > 0 else 0.0)

        # 盈亏比
        avg_win = strategy_returns[winning_trades].mean() if winning_trades.sum() > 0 else 0.0
        avg_loss = strategy_returns[~winning_trades].mean() if (~winning_trades).sum() > 0 else 0.0
        metrics['profit_loss_ratio'] = float(abs(avg_win / avg_loss) if avg_loss != 0 else 0.0)

    except Exception as e:
        # 计算失败时记录错误
        metrics['strategy_error'] = str(e)

    return metrics


def calculate_all_metrics(y_true: Union[np.ndarray, Any],
                         y_pred: Union[np.ndarray, Any],
                         task_type: str = 'regression',
                         **kwargs) -> Dict[str, float]:
    """
    计算所有相关指标

    Args:
        y_true: 真实值
        y_pred: 预测值
        task_type: 任务类型 'regression' 或 'classification'
        **kwargs: 其他参数，如feature_scaler, y_prob等

    Returns:
        合并的指标字典
    """
    # 转换为numpy数组
    if TORCH_AVAILABLE and torch is not None:
        if isinstance(y_true, torch.Tensor):
            y_true = y_true.cpu().numpy()
        if isinstance(y_pred, torch.Tensor):
            y_pred = y_pred.cpu().numpy()

    all_metrics = {}

    if task_type == 'regression':
        # 回归指标
        reg_metrics = regression_metrics(y_true, y_pred, kwargs.get('feature_scaler'))
        all_metrics.update(reg_metrics)

        # 尝试计算金融指标（假设y_true和y_pred是涨跌幅）
        try:
            fin_metrics = financial_metrics(y_true, y_pred)
            all_metrics.update(fin_metrics)
        except:
            pass

    elif task_type == 'classification':
        # 分类指标
        # 对于分类，y_pred可能是概率或类别标签
        y_pred_labels = y_pred
        y_prob = kwargs.get('y_prob')

        # 如果y_pred是概率（二维数组），取argmax作为预测标签
        if y_pred.ndim > 1 and y_pred.shape[1] > 1:
            y_pred_labels = np.argmax(y_pred, axis=1)
            if y_prob is None:
                y_prob = y_pred

        cls_metrics = classification_metrics(y_true, y_pred_labels, y_prob)
        all_metrics.update(cls_metrics)

    # 添加样本数量信息
    all_metrics['n_samples'] = len(y_true)

    return all_metrics


def compare_models(metrics_list: List[Dict[str, float]],
                  model_names: List[str]) -> pd.DataFrame:
    """
    比较多个模型的评估指标

    Args:
        metrics_list: 每个模型的指标字典列表
        model_names: 模型名称列表

    Returns:
        比较表格DataFrame
    """
    if len(metrics_list) != len(model_names):
        raise ValueError("metrics_list和model_names长度必须相同")

    # 创建DataFrame
    df = pd.DataFrame(metrics_list, index=model_names)

    # 按行排序（指标作为列）
    return df.T  # 转置，使模型作为列，指标作为行


def print_metrics_report(metrics: Dict[str, float], title: str = "评估报告"):
    """
    打印格式化的评估报告

    Args:
        metrics: 指标字典
        title: 报告标题
    """
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")

    # 分组显示指标
    metric_groups = {
        '基础指标': ['mse', 'mae', 'rmse', 'r2', 'accuracy', 'precision', 'recall', 'f1', 'auc'],
        '金融指标': ['direction_accuracy', 'correlation', 'strategy_return',
                   'benchmark_return', 'excess_return', 'sharpe_ratio',
                   'max_drawdown', 'win_rate', 'profit_loss_ratio'],
        '样本信息': ['n_samples', 'class_accuracy_mean', 'class_accuracy_std']
    }

    for group_name, group_metrics in metric_groups.items():
        group_items = {}
        for metric in group_metrics:
            if metric in metrics:
                value = metrics[metric]
                # 格式化输出
                if isinstance(value, float):
                    if metric in ['mse', 'mae', 'rmse']:
                        group_items[metric] = f"{value:.6f}"
                    elif metric in ['r2', 'accuracy', 'precision', 'recall', 'f1', 'auc',
                                  'direction_accuracy', 'correlation', 'win_rate']:
                        group_items[metric] = f"{value:.4f}"
                    elif metric in ['strategy_return', 'benchmark_return', 'excess_return',
                                  'sharpe_ratio', 'max_drawdown', 'profit_loss_ratio']:
                        group_items[metric] = f"{value:.4f}"
                    else:
                        group_items[metric] = f"{value:.4f}"
                else:
                    group_items[metric] = str(value)

        if group_items:
            print(f"\n{group_name}:")
            for metric, value in group_items.items():
                print(f"  {metric:25s}: {value}")


# 测试代码
if __name__ == "__main__":
    # 测试回归指标
    print("测试回归指标...")
    y_true_reg = np.random.randn(100)
    y_pred_reg = y_true_reg + np.random.randn(100) * 0.1
    reg_metrics = calculate_all_metrics(y_true_reg, y_pred_reg, 'regression')
    print_metrics_report(reg_metrics, "回归测试报告")

    # 测试分类指标
    print("\n\n测试分类指标...")
    y_true_cls = np.random.randint(0, 3, 100)
    y_prob_cls = np.random.rand(100, 3)
    y_pred_cls = np.argmax(y_prob_cls, axis=1)
    cls_metrics = calculate_all_metrics(y_true_cls, y_pred_cls, 'classification', y_prob=y_prob_cls)
    print_metrics_report(cls_metrics, "分类测试报告")

    # 测试金融指标
    print("\n\n测试金融指标...")
    y_true_fin = np.random.randn(100) * 0.01  # 模拟每日涨跌幅
    y_pred_fin = y_true_fin + np.random.randn(100) * 0.005
    fin_metrics = financial_metrics(y_true_fin, y_pred_fin)
    print_metrics_report(fin_metrics, "金融指标测试报告")