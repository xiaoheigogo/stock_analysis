"""
FastAPI Web应用程序入口点

提供股票预测和推荐的RESTful API接口
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import yaml
import logging

from utils.logger import logger
from recommendation_system import RecommendationSystem, Recommendation

# 创建FastAPI应用
app = FastAPI(
    title="股票预测系统API",
    description="基于机器学习的股票趋势预测和推荐系统",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境中应限制来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置静态文件和模板
frontend_dir = project_root / "frontend"
static_dir = frontend_dir / "static"
templates_dir = frontend_dir / "templates"

# 创建目录（如果不存在）
static_dir.mkdir(parents=True, exist_ok=True)
templates_dir.mkdir(parents=True, exist_ok=True)

# 挂载静态文件
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 配置模板
templates = Jinja2Templates(directory=str(templates_dir))

# 全局变量
recommendation_system = None
config = None

# Pydantic模型
class StockPredictionRequest(BaseModel):
    """股票预测请求模型"""
    ts_code: str
    seq_len: Optional[int] = 30
    pred_len: Optional[int] = 10

class StockPredictionResponse(BaseModel):
    """股票预测响应模型"""
    ts_code: str
    ts_name: str
    predicted_return: float
    confidence: float
    risk_score: float
    industry: str
    reasons: List[str]

class StockRecommendationResponse(BaseModel):
    """股票推荐响应模型"""
    recommendations: List[StockPredictionResponse]
    date: str
    count: int

class StockDataResponse(BaseModel):
    """股票数据响应模型"""
    ts_code: str
    ts_name: str
    data: List[Dict[str, Any]]
    count: int
    date_range: Dict[str, str]

class HealthResponse(BaseModel):
    """健康检查响应模型"""
    status: str
    version: str
    database: str
    model_available: bool

# 启动事件
@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    global recommendation_system, config

    logger.info("正在启动股票预测API服务...")

    try:
        # 加载配置
        config_path = project_root / "config.yaml"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 初始化推荐系统（加载最佳模型）
        model_path = project_root / "output" / "models" / "best_model.pth"
        if model_path.exists():
            recommendation_system = RecommendationSystem(model_path=str(model_path))
            logger.info(f"推荐系统初始化完成，已加载模型: {model_path}")
        else:
            logger.warning(f"模型文件不存在: {model_path}，使用随机预测")
            recommendation_system = RecommendationSystem()

        logger.info(f"API服务启动完成，监听 {config.get('api', {}).get('host', '0.0.0.0')}:{config.get('api', {}).get('port', 8000)}")

    except Exception as e:
        logger.error(f"启动失败: {e}")
        raise

# API端点
@app.get("/")
async def root(request: Request):
    """根端点 - 返回前端页面"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/")
async def api_root():
    """API根端点"""
    return {
        "service": "股票预测系统API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/api/health",
            "predict": "/api/predict (POST)",
            "recommend": "/api/recommend",
            "stock_data": "/api/stock/{ts_code}"
        }
    }

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """健康检查端点"""
    from utils.db_conn import postgres

    db_status = "unknown"
    try:
        with postgres.get_cursor() as cur:
            cur.execute("SELECT 1")
            db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return HealthResponse(
        status="healthy",
        version="1.0.0",
        database=db_status,
        model_available=recommendation_system.model is not None
    )

@app.post("/api/predict", response_model=StockPredictionResponse)
async def predict_stock(request: StockPredictionRequest):
    """
    预测单只股票趋势

    Args:
        request: 预测请求参数

    Returns:
        预测结果
    """
    try:
        logger.info(f"预测请求: {request.ts_code}")

        # 使用推荐系统进行预测
        predictions_df = recommendation_system.batch_predict(
            [request.ts_code],
            seq_len=request.seq_len,
            pred_len=request.pred_len
        )

        if predictions_df.empty:
            raise HTTPException(status_code=404, detail=f"股票 {request.ts_code} 预测失败")

        row = predictions_df.iloc[0]

        # 创建推荐对象以生成理由
        rec = Recommendation(
            ts_code=row['ts_code'],
            ts_name=row['ts_name'],
            predicted_return=float(row['predicted_return']),
            confidence=float(row['confidence']),
            risk_score=float(row['risk_score']),
            industry=row['industry'],
            current_price=float(row.get('current_price', 0.0))
        )
        rec.reasons = recommendation_system._generate_reasons(rec)

        return StockPredictionResponse(
            ts_code=rec.ts_code,
            ts_name=rec.ts_name,
            predicted_return=rec.predicted_return,
            confidence=rec.confidence,
            risk_score=rec.risk_score,
            industry=rec.industry,
            reasons=rec.reasons
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"预测失败: {e}")
        raise HTTPException(status_code=500, detail=f"预测失败: {str(e)}")

@app.get("/api/recommend", response_model=StockRecommendationResponse)
async def get_recommendations(
    top_n: int = Query(10, description="推荐数量", ge=1, le=50),
    max_risk: float = Query(0.5, description="最大风险阈值", ge=0.0, le=1.0),
    min_confidence: float = Query(0.6, description="最小置信度阈值", ge=0.0, le=1.0)
):
    """
    获取今日推荐股票

    Args:
        top_n: 推荐数量
        max_risk: 最大风险阈值
        min_confidence: 最小置信度阈值

    Returns:
        推荐股票列表
    """
    try:
        logger.info(f"获取推荐: top_n={top_n}, max_risk={max_risk}, min_confidence={min_confidence}")

        # 获取测试股票列表（实际应用中应该获取全市场股票）
        from utils.db_conn import postgres
        sql = "SELECT ts_code FROM stock_list LIMIT 20"
        df = postgres.select_df(sql)
        test_codes = df['ts_code'].tolist()

        # 批量预测
        predictions_df = recommendation_system.batch_predict(
            test_codes,
            seq_len=30,
            pred_len=10
        )

        if predictions_df.empty:
            raise HTTPException(status_code=500, detail="预测结果为空")

        # 生成推荐
        recommendations = recommendation_system.generate_recommendations(
            predictions_df,
            top_n=top_n,
            max_risk=max_risk,
            min_confidence=min_confidence
        )

        # 转换为响应模型
        recommendation_responses = []
        for rec in recommendations:
            recommendation_responses.append(
                StockPredictionResponse(
                    ts_code=rec.ts_code,
                    ts_name=rec.ts_name,
                    predicted_return=rec.predicted_return,
                    confidence=rec.confidence,
                    risk_score=rec.risk_score,
                    industry=rec.industry,
                    reasons=rec.reasons
                )
            )

        # 保存推荐结果
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        recommendation_system.save_recommendations(recommendations, date=today)

        return StockRecommendationResponse(
            recommendations=recommendation_responses,
            date=today,
            count=len(recommendation_responses)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取推荐失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取推荐失败: {str(e)}")

@app.get("/api/stock/{ts_code}", response_model=StockDataResponse)
async def get_stock_data(
    ts_code: str,
    limit: int = Query(100, description="数据条数", ge=1, le=1000),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    获取股票历史数据

    Args:
        ts_code: 股票代码
        limit: 数据条数限制
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)

    Returns:
        股票历史数据
    """
    try:
        logger.info(f"获取股票数据: {ts_code}, limit={limit}")

        from utils.db_conn import postgres

        # 获取股票基本信息
        sql_info = """
            SELECT ts_code, ts_name, industry, list_date
            FROM stock_list
            WHERE ts_code = %s
        """
        stock_info = postgres.select(sql_info, params=(ts_code,), fetch_one=True)

        if not stock_info:
            raise HTTPException(status_code=404, detail=f"股票 {ts_code} 不存在")

        # 构建数据查询
        where_clauses = ["ts_code = %s"]
        params = [ts_code]

        if start_date:
            where_clauses.append("trade_date >= %s")
            params.append(start_date)
        if end_date:
            where_clauses.append("trade_date <= %s")
            params.append(end_date)

        where_sql = " AND ".join(where_clauses)

        sql_data = f"""
            SELECT trade_date, open_raw, high_raw, low_raw, close_raw,
                   volumn_raw, amount_raw, amplitude_raw, pct_change_raw,
                   change_raw, turnover_raw
            FROM daily_kline
            WHERE {where_sql}
            ORDER BY trade_date DESC
            LIMIT %s
        """
        params.append(limit)

        data = postgres.select(sql_data, params=tuple(params))

        # 获取日期范围
        sql_range = f"""
            SELECT MIN(trade_date) as min_date, MAX(trade_date) as max_date
            FROM daily_kline
            WHERE ts_code = %s
        """
        date_range = postgres.select(sql_range, params=(ts_code,), fetch_one=True)

        return StockDataResponse(
            ts_code=stock_info['ts_code'],
            ts_name=stock_info['ts_name'],
            data=data,
            count=len(data),
            date_range={
                "min_date": str(date_range['min_date']) if date_range['min_date'] else "",
                "max_date": str(date_range['max_date']) if date_range['max_date'] else ""
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取股票数据失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取股票数据失败: {str(e)}")

# 错误处理器
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """HTTP异常处理"""
    return {
        "error": exc.detail,
        "status_code": exc.status_code
    }

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """通用异常处理"""
    logger.error(f"未处理的异常: {exc}", exc_info=True)
    return {
        "error": "内部服务器错误",
        "detail": str(exc),
        "status_code": 500
    }