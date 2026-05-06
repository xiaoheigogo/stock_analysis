// 股票预测系统前端应用

// 全局变量
let stockChart = null;
let app = null;

// Vue应用初始化
document.addEventListener('DOMContentLoaded', function() {
    // 创建Vue应用
    app = Vue.createApp({
        data() {
            return {
                // 视图状态
                currentView: 'home',
                apiStatus: 'unknown',
                dbStatus: 'unknown',
                modelAvailable: false,
                stockCount: 0,
                latestDataDate: 'N/A',

                // 个股搜索
                searchCode: '',
                autoCompleteResults: [],
                selectedStock: null,
                predictionDays: 10,
                predictionResult: null,

                // 推荐股票
                recommendations: [],
                recommendationFilter: 'all',

                // K线图
                chartStockCode: '000001',
                chartPeriod: '1y',
                indicators: {
                    ma5: true,
                    ma10: true,
                    macd: false,
                    rsi: false
                },

                // 历史预测
                historyData: [],
                historyStartDate: '',
                historyEndDate: '',
                accuracyStats: {
                    direction_accuracy: 0,
                    avg_return: 0,
                    avg_confidence: 0,
                    total_count: 0
                },

                // 模态框
                modalStockDetail: null
            };
        },

        computed: {
            // 过滤后的推荐列表
            filteredRecommendations() {
                if (this.recommendationFilter === 'all') {
                    return this.recommendations;
                } else if (this.recommendationFilter === 'high_return') {
                    return this.recommendations.filter(r => r.predicted_return > 0.05);
                } else if (this.recommendationFilter === 'low_risk') {
                    return this.recommendations.filter(r => r.risk_score < 0.3);
                }
                return this.recommendations;
            }
        },

        created() {
            // 初始化日期范围
            const today = new Date();
            const oneMonthAgo = new Date();
            oneMonthAgo.setMonth(today.getMonth() - 1);

            this.historyStartDate = oneMonthAgo.toISOString().split('T')[0];
            this.historyEndDate = today.toISOString().split('T')[0];

            // 初始化检查
            this.checkApiHealth();
            this.fetchRecommendations();
        },

        methods: {
            // 检查API健康状态
            async checkApiHealth() {
                try {
                    const response = await axios.get('/api/health');
                    if (response.data.status === 'healthy') {
                        this.apiStatus = 'healthy';
                        this.dbStatus = response.data.database;
                        this.modelAvailable = response.data.model_available;

                        // 获取系统状态信息
                        this.fetchSystemStatus();
                    }
                } catch (error) {
                    console.error('API健康检查失败:', error);
                    this.apiStatus = 'unhealthy';
                }
            },

            // 获取系统状态信息
            async fetchSystemStatus() {
                try {
                    // 获取股票总数
                    const stockResponse = await axios.post('/api/predict', {
                        ts_code: '000001',
                        seq_len: 30,
                        pred_len: 10
                    });

                    // 从根端点获取信息
                    const rootResponse = await axios.get('/');
                    if (rootResponse.data && rootResponse.data.version) {
                        console.log('系统版本:', rootResponse.data.version);
                    }
                } catch (error) {
                    console.error('获取系统状态失败:', error);
                }
            },

            // 自动完成股票搜索
            async autoCompleteStock() {
                if (this.searchCode.length < 2) {
                    this.autoCompleteResults = [];
                    return;
                }

                try {
                    // 从推荐API获取真实股票列表
                    const resp = await axios.get('/api/recommend', { params: { top_n: 20 } });
                    const stocks = (resp.data.recommendations || []).map(r => ({
                        ts_code: r.ts_code,
                        ts_name: r.ts_name,
                        industry: r.industry || ''
                    }));
                    this.autoCompleteResults = stocks.filter(stock =>
                        stock.ts_code.includes(this.searchCode) ||
                        stock.ts_name.includes(this.searchCode)
                    ).slice(0, 5);
                } catch (error) {
                    console.error('自动完成失败:', error);
                    this.autoCompleteResults = [];
                }
            },

            // 选择股票
            selectStock(stock) {
                this.selectedStock = stock;
                this.searchCode = stock.ts_code;
                this.autoCompleteResults = [];
            },

            // 搜索股票
            async searchStock() {
                if (!this.searchCode) {
                    alert('请输入股票代码');
                    return;
                }

                try {
                    // 从推荐API获取真实股票信息
                    const resp = await axios.get('/api/recommend', { params: { top_n: 50 } });
                    const found = (resp.data.recommendations || []).find(r => r.ts_code === this.searchCode);
                    this.selectedStock = found || {
                        ts_code: this.searchCode,
                        ts_name: '未找到',
                        industry: '未知',
                        list_date: ''
                    };

                    // 清除之前的预测结果
                    this.predictionResult = null;
                } catch (error) {
                    console.error('搜索股票失败:', error);
                    this.selectedStock = { ts_code: this.searchCode, ts_name: '查询失败', industry: '', list_date: '' };
                }
            },

            // 预测股票
            async predictStock() {
                if (!this.selectedStock) {
                    alert('请先选择股票');
                    return;
                }

                try {
                    // 显示加载状态
                    const button = event?.target;
                    const originalText = button?.innerHTML;
                    if (button) {
                        button.innerHTML = '<span class="loading-spinner"></span> 预测中...';
                        button.disabled = true;
                    }

                    // 调用预测API
                    const response = await axios.post('/api/predict', {
                        ts_code: this.selectedStock.ts_code,
                        seq_len: 30,
                        pred_len: parseInt(this.predictionDays)
                    });

                    this.predictionResult = response.data;
                    this.currentView = 'search';

                    // 恢复按钮状态
                    if (button) {
                        button.innerHTML = originalText;
                        button.disabled = false;
                    }

                    // 显示成功消息
                    this.showToast('预测完成', '预测结果已生成', 'success');
                } catch (error) {
                    console.error('预测失败:', error);
                    alert('预测失败: ' + (error.response?.data?.detail || error.message));

                    // 恢复按钮状态
                    const button = event?.target;
                    if (button) {
                        button.innerHTML = '<i class="bi bi-lightning-charge"></i> 开始预测';
                        button.disabled = false;
                    }
                }
            },

            // 获取推荐股票
            async fetchRecommendations() {
                try {
                    // 显示加载状态
                    this.recommendations = [];

                    // 调用推荐API
                    const response = await axios.get('/api/recommend', {
                        params: {
                            top_n: 10,
                            max_risk: 0.5,
                            min_confidence: 0.6
                        }
                    });

                    this.recommendations = response.data.recommendations;
                    this.showToast('推荐更新', `已获取${this.recommendations.length}个推荐`, 'success');
                } catch (error) {
                    console.error('获取推荐失败:', error);
                    this.recommendations = [];
                    this.showToast('获取失败', 'API调用失败，请稍后重试', 'error');
                }
            },

            // 加载K线图
            async loadChart() {
                if (!this.chartStockCode) {
                    alert('请输入股票代码');
                    return;
                }

                try {
                    // 获取股票数据
                    const response = await axios.get(`/api/stock/${this.chartStockCode}`, {
                        params: {
                            limit: 100,
                            start_date: this.calculateStartDate()
                        }
                    });

                    // 解析数据
                    const chartData = response.data.data;
                    if (chartData.length === 0) {
                        alert('该股票无历史数据');
                        return;
                    }

                    // 准备图表数据
                    const dates = chartData.map(item => item.trade_date);
                    const prices = chartData.map(item => ({
                        open: item.open_raw,
                        close: item.close_raw,
                        low: item.low_raw,
                        high: item.high_raw
                    }));

                    // 渲染图表
                    this.renderChart(dates, prices);

                } catch (error) {
                    console.error('加载图表失败:', error);
                    this.showToast('加载失败', 'K线数据加载失败，请稍后重试', 'error');
                    this.renderChart([], []);
                    this.showToast('使用模拟数据', 'API调用失败，使用示例数据', 'warning');
                }
            },

            // 计算开始日期
            calculateStartDate() {
                const today = new Date();
                const startDate = new Date(today);

                switch (this.chartPeriod) {
                    case '1m':
                        startDate.setMonth(today.getMonth() - 1);
                        break;
                    case '3m':
                        startDate.setMonth(today.getMonth() - 3);
                        break;
                    case '6m':
                        startDate.setMonth(today.getMonth() - 6);
                        break;
                    case '1y':
                        startDate.setFullYear(today.getFullYear() - 1);
                        break;
                    case 'all':
                        return null; // 全部数据
                    default:
                        startDate.setMonth(today.getMonth() - 1);
                }

                return startDate.toISOString().split('T')[0];
            },

            // 渲染图表
            renderChart(dates, prices) {
                // 初始化ECharts实例
                const chartDom = document.getElementById('chart-container');
                if (stockChart) {
                    stockChart.dispose();
                }
                stockChart = echarts.init(chartDom);

                // 准备K线图数据
                const klineData = [];
                for (let i = 0; i < dates.length; i++) {
                    klineData.push([
                        dates[i],
                        prices[i].open,
                        prices[i].close,
                        prices[i].low,
                        prices[i].high
                    ]);
                }

                // 配置选项
                const option = {
                    title: {
                        text: `${this.chartStockCode} K线图`,
                        left: 'center'
                    },
                    tooltip: {
                        trigger: 'axis',
                        axisPointer: {
                            type: 'cross'
                        },
                        formatter: function(params) {
                            const data = params[0];
                            return `
                                <div style="font-weight: bold;">${data.axisValue}</div>
                                <div>开盘: ${data.value[1].toFixed(2)}</div>
                                <div>收盘: ${data.value[2].toFixed(2)}</div>
                                <div>最低: ${data.value[3].toFixed(2)}</div>
                                <div>最高: ${data.value[4].toFixed(2)}</div>
                            `;
                        }
                    },
                    grid: {
                        left: '10%',
                        right: '10%',
                        bottom: '15%'
                    },
                    xAxis: {
                        type: 'category',
                        data: dates,
                        scale: true,
                        boundaryGap: false,
                        axisLine: { onZero: false },
                        splitLine: { show: false },
                        min: 'dataMin',
                        max: 'dataMax'
                    },
                    yAxis: {
                        scale: true,
                        splitArea: {
                            show: true
                        }
                    },
                    dataZoom: [
                        {
                            type: 'inside',
                            start: 0,
                            end: 100
                        },
                        {
                            show: true,
                            type: 'slider',
                            top: '90%',
                            start: 0,
                            end: 100
                        }
                    ],
                    series: [
                        {
                            name: 'K线',
                            type: 'candlestick',
                            data: klineData,
                            itemStyle: {
                                color: '#ec0000',
                                color0: '#00da3c',
                                borderColor: '#8A0000',
                                borderColor0: '#008F28'
                            }
                        }
                    ]
                };

                // 添加技术指标
                if (this.indicators.ma5 || this.indicators.ma10) {
                    const maSeries = [];

                    if (this.indicators.ma5) {
                        const ma5Data = this.calculateMA(5, klineData);
                        maSeries.push({
                            name: 'MA5',
                            type: 'line',
                            data: ma5Data,
                            smooth: true,
                            lineStyle: {
                                width: 2,
                                color: '#ff7f0e'
                            },
                            showSymbol: false
                        });
                    }

                    if (this.indicators.ma10) {
                        const ma10Data = this.calculateMA(10, klineData);
                        maSeries.push({
                            name: 'MA10',
                            type: 'line',
                            data: ma10Data,
                            smooth: true,
                            lineStyle: {
                                width: 2,
                                color: '#2ca02c'
                            },
                            showSymbol: false
                        });
                    }

                    option.series.push(...maSeries);
                }

                // 设置图表选项
                stockChart.setOption(option);

                // 窗口大小变化时重绘
                window.addEventListener('resize', function() {
                    stockChart.resize();
                });
            },

            // 计算移动平均线
            calculateMA(period, klineData) {
                const result = [];
                for (let i = 0; i < klineData.length; i++) {
                    if (i < period - 1) {
                        result.push('-');
                    } else {
                        let sum = 0;
                        for (let j = 0; j < period; j++) {
                            sum += klineData[i - j][2]; // 使用收盘价
                        }
                        result.push((sum / period).toFixed(2));
                    }
                }
                return result;
            },

            // 更新图表
            updateChart() {
                if (stockChart) {
                    this.loadChart();
                }
            },

            // 加载股票图表
            loadStockChart() {
                if (this.selectedStock) {
                    this.chartStockCode = this.selectedStock.ts_code;
                    this.currentView = 'charts';
                    setTimeout(() => this.loadChart(), 100);
                }
            },

            // 查看股票详情
            viewStockDetail(stock) {
                this.modalStockDetail = {
                    ...stock,
                    current_price: null,
                    market_cap: null,
                    trade_status: '正常交易'
                };

                // 显示模态框
                const modal = new bootstrap.Modal(document.getElementById('stockDetailModal'));
                modal.show();
            },

            // 预测模态框中的股票
            predictModalStock() {
                if (this.modalStockDetail) {
                    this.selectedStock = this.modalStockDetail;
                    this.searchCode = this.modalStockDetail.ts_code;
                    this.currentView = 'search';

                    // 关闭模态框
                    const modal = bootstrap.Modal.getInstance(document.getElementById('stockDetailModal'));
                    modal.hide();

                    // 延迟执行预测
                    setTimeout(() => this.predictStock(), 300);
                }
            },

            // 预测单个股票（从推荐列表）
            async predictSingleStock(tsCode) {
                try {
                    this.searchCode = tsCode;
                    this.selectedStock = {
                        ts_code: tsCode,
                        ts_name: tsCode,
                        industry: '未知',
                        list_date: 'N/A'
                    };

                    // 调用预测API
                    const response = await axios.post('/api/predict', {
                        ts_code: tsCode,
                        seq_len: 30,
                        pred_len: parseInt(this.predictionDays)
                    });

                    this.predictionResult = response.data;
                    this.currentView = 'search';

                    this.showToast('预测完成', '预测结果已生成', 'success');
                } catch (error) {
                    console.error('预测失败:', error);
                    alert('预测失败: ' + (error.response?.data?.detail || error.message));
                }
            },

            // 加载历史预测
            async loadHistory() {
                try {
                    // 等待后端实现历史预测API
                    this.historyData = [];
                    this.calculateAccuracyStats();
                    this.showToast('提示', '历史预测功能开发中，敬请期待', 'info');
                } catch (error) {
                    console.error('加载历史数据失败:', error);
                    this.showToast('加载失败', '历史数据加载失败', 'danger');
                }
            },

            // 计算准确率统计
            calculateAccuracyStats() {
                if (this.historyData.length === 0) {
                    this.accuracyStats = {
                        direction_accuracy: 0,
                        avg_return: 0,
                        avg_confidence: 0,
                        total_count: 0
                    };
                    return;
                }

                const validData = this.historyData.filter(item => item.direction_correct !== null);
                const directionCorrect = validData.filter(item => item.direction_correct).length;

                this.accuracyStats = {
                    direction_accuracy: validData.length > 0 ? directionCorrect / validData.length : 0,
                    avg_return: this.historyData.reduce((sum, item) => sum + item.predicted_return, 0) / this.historyData.length,
                    avg_confidence: 0.7, // 模拟值
                    total_count: this.historyData.length
                };
            },

            // 查看历史详情
            viewHistoryDetail(item) {
                alert(`详情查看:\n日期: ${item.date}\n股票: ${item.ts_code}\n预测收益: ${(item.predicted_return * 100).toFixed(2)}%\n实际收益: ${item.actual_return ? (item.actual_return * 100).toFixed(2) + '%' : 'N/A'}`);
            },

            // 清空历史
            clearHistory() {
                this.historyData = [];
                this.accuracyStats = {
                    direction_accuracy: 0,
                    avg_return: 0,
                    avg_confidence: 0,
                    total_count: 0
                };
                this.showToast('已清空', '历史数据已清空', 'info');
            },

            // 刷新推荐
            refreshRecommendations() {
                this.fetchRecommendations();
            },

            // 测试预测
            testPrediction() {
                this.currentView = 'search';
                this.searchCode = '000001';
                setTimeout(() => this.searchStock(), 100);
            },

            // 显示系统信息
            showSystemInfo() {
                alert('股票预测系统 v1.0.0\n基于机器学习的时间序列分析\n后端API: FastAPI\n前端框架: Vue.js 3\n图表库: ECharts\n数据库: PostgreSQL');
            },

            // 导出推荐
            exportRecommendations() {
                const dataStr = JSON.stringify(this.recommendations, null, 2);
                const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);

                const exportFileDefaultName = `stock_recommendations_${new Date().toISOString().split('T')[0]}.json`;

                const linkElement = document.createElement('a');
                linkElement.setAttribute('href', dataUri);
                linkElement.setAttribute('download', exportFileDefaultName);
                linkElement.click();

                this.showToast('导出成功', '推荐数据已导出为JSON文件', 'success');
            },

            // 显示Toast消息
            showToast(title, message, type = 'info') {
                // 创建Toast元素
                const toastId = 'toast-' + Date.now();
                const toastHtml = `
                    <div id="${toastId}" class="toast align-items-center text-bg-${type} border-0" role="alert">
                        <div class="d-flex">
                            <div class="toast-body">
                                <strong>${title}</strong>: ${message}
                            </div>
                            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                        </div>
                    </div>
                `;

                // 添加到页面
                const toastContainer = document.querySelector('.toast-container');
                if (!toastContainer) {
                    const container = document.createElement('div');
                    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
                    document.body.appendChild(container);
                    container.innerHTML = toastHtml;
                } else {
                    toastContainer.innerHTML = toastHtml;
                }

                // 显示Toast
                const toastElement = document.getElementById(toastId);
                const toast = new bootstrap.Toast(toastElement);
                toast.show();

                // 自动移除
                setTimeout(() => {
                    if (toastElement && toastElement.parentNode) {
                        toastElement.parentNode.removeChild(toastElement);
                    }
                }, 5000);
            }
        }
    });

    // 挂载应用
    app.mount('#app');

    // 初始加载
    console.log('股票预测系统前端已初始化');

    // 检查API可用性
    setTimeout(() => {
        if (app) {
            app.checkApiHealth();
        }
    }, 1000);
});

// 全局工具函数
function formatDate(date) {
    return new Date(date).toLocaleDateString('zh-CN');
}

function formatCurrency(value) {
    return new Intl.NumberFormat('zh-CN', {
        style: 'currency',
        currency: 'CNY'
    }).format(value);
}

function formatPercent(value) {
    return (value * 100).toFixed(2) + '%';
}