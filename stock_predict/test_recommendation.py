#!/usr/bin/env python3
"""
测试推荐系统
"""

import sys
import os
import pandas as pd

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from recommendation_system import RecommendationSystem, Recommendation

def test_recommendation_system():
    """测试推荐系统"""
    print("测试推荐系统...")

    # 创建推荐系统实例（无模型）
    rs = RecommendationSystem()

    # 测试股票代码
    test_codes = ["000001", "000002", "000003", "000004", "000005"]

    # 测试批量预测
    print("\n1. 测试批量预测...")
    predictions = rs.batch_predict(test_codes, seq_len=30, pred_len=10)

    if not predictions.empty:
        print(f"  预测结果形状: {predictions.shape}")
        print(f"  前3条预测结果:")
        print(predictions.head(3).to_string())
    else:
        print("  预测结果为空")

    # 测试推荐生成
    print("\n2. 测试推荐生成...")
    if not predictions.empty:
        recommendations = rs.generate_recommendations(
            predictions, top_n=3, max_risk=0.5, min_confidence=0.6
        )

        print(f"  生成推荐数: {len(recommendations)}")
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec.ts_code} {rec.ts_name}: "
                  f"预期收益={rec.predicted_return:.2%}, "
                  f"置信度={rec.confidence:.2f}, "
                  f"风险={rec.risk_score:.2f}")
            print(f"     理由: {', '.join(rec.reasons[:2])}")

    # 测试推荐保存
    print("\n3. 测试推荐保存...")
    if recommendations:
        success = rs.save_recommendations(recommendations, date="2024-01-01")
        print(f"  保存推荐结果: {'成功' if success else '失败'}")

    # 测试数据结构
    print("\n4. 测试数据结构...")
    rec = Recommendation(
        ts_code="000001",
        ts_name="测试股票",
        predicted_return=0.05,
        confidence=0.8,
        risk_score=0.3,
        industry="金融",
        market_cap=1000.0,
        current_price=10.0,
        reasons=["预期涨幅超过5%", "模型预测置信度高"]
    )

    print(f"  推荐对象创建成功:")
    print(f"    代码: {rec.ts_code}")
    print(f"    名称: {rec.ts_name}")
    print(f"    预期收益: {rec.predicted_return:.2%}")
    print(f"    置信度: {rec.confidence:.2f}")
    print(f"    风险评分: {rec.risk_score:.2f}")
    print(f"    行业: {rec.industry}")
    print(f"    理由: {rec.reasons}")

    # 测试转换为字典
    rec_dict = rec.to_dict()
    print(f"  转换为字典: {list(rec_dict.keys())}")

def test_recommendation_table_creation():
    """测试推荐结果表创建"""
    print("\n\n测试推荐结果表创建...")

    try:
        from recommendation_system import create_recommendation_table
        success = create_recommendation_table()
        print(f"  创建推荐结果表: {'成功' if success else '失败'}")
    except Exception as e:
        print(f"  创建推荐结果表失败: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("股票推荐系统测试")
    print("=" * 60)

    test_recommendation_system()
    test_recommendation_table_creation()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)