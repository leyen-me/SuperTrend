from longport.openapi import Config, QuoteContext, TradeContext, OrderType, OrderSide, TimeInForceType, OutsideRTH
import logging
from decimal import Decimal
from flask import Flask, request, jsonify
import datetime
from flask_cors import CORS
import time

# ==================== Settings ====================
# 做多的ETF
DO_LONG_SYMBOL = "TSLL.US"
# 做空的ETF
DO_SHORT_SYMBOL = "TSDD.US"


# ==================== init ====================
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

config = Config.from_env()
trade_ctx = TradeContext(config)


# ==================== Function ====================
def buy(symbol):
    try:
        # 获取最大买入数量
        max_buy_resp = trade_ctx.estimate_max_purchase_quantity(
            symbol=symbol,
            order_type=OrderType.MO,
            side=OrderSide.Buy
        )
        # 90%的现金仓位
        cash_qty = int(int(max_buy_resp.cash_max_qty) * 0.9)
        trade_ctx.submit_order(
            symbol,
            OrderType.MO,
            OrderSide.Buy,
            Decimal(cash_qty),
            TimeInForceType.Day,
            outside_rth=OutsideRTH.AnyTime
        )
        logger.info(f"买入订单执行完成 - 股票：{symbol}，数量：{cash_qty}")
    except Exception as e:
        logger.error(f"买入执行失败：{e}")


def sell(symbol, quantity):
    try:
        trade_ctx.submit_order(
            symbol,
            OrderType.MO,
            OrderSide.Sell,
            Decimal(quantity),
            TimeInForceType.Day,
            outside_rth=OutsideRTH.AnyTime
        )
        logger.info(f"卖出订单执行完成 - 股票：{symbol}，数量：{quantity}")
    except Exception as e:
        logger.error(f"卖出执行失败：{e}")


def do_long():
    """
    做多
    """
    buy(DO_LONG_SYMBOL)
    

def do_short():
    """
    做空
    """
    buy(DO_SHORT_SYMBOL)


def do_close_position():
    """
    平仓
    """
    # 获取持仓信息
    stock_positions = []
    try:
        resp = trade_ctx.stock_positions()
        stock_positions = resp.channels
    except Exception as e:
        logger.error(f"获取持仓数量失败：{e}")

    # 平仓动作
    for channel in stock_positions:
        for position in channel.positions:
            if position.symbol == DO_LONG_SYMBOL or position.symbol == DO_SHORT_SYMBOL:
                if position.quantity > 0 and position.quantity < 1:
                    sell(position.symbol, position.quantity)
                else:
                    # 碎骨单
                    logger.error(f"持仓数量为0")


# ==================== Main ====================
@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        webhook_data = request.json
        logger.info(f"收到TradingView信号=======>")
        logger.info(f"{webhook_data}")
        
        # 获取交易动作和市场位置信息
        action = webhook_data.get('action')
        sentiment = webhook_data.get('sentiment')
        
        if not action or not sentiment:
            """
            {
                "ticker": "{{ticker}}",
                "time": "{{time}}",
                "action": "{{strategy.order.action}}",
                "sentiment": "{{strategy.market_position}}",
                "price": "{{strategy.order.price}}"
            }
            """
            logger.error("信号数据不完整，缺少action或sentiment")
            return jsonify({'error': '信号数据不完整'}), 400
            
        logger.info(f"交易信号: action={action}, position={sentiment}")
        
        # 根据信号执行交易
        if action == "buy" and sentiment == "long":
            # 开多仓
            logger.info("执行开多仓操作")
            do_close_position()
            time.sleep(4)
            do_long()
        elif action == "sell" and sentiment == "short":
            # 开空仓
            logger.info("执行开空仓操作")
            do_close_position()
            time.sleep(4)
            do_short()
        elif (action == "sell" and sentiment == "flat") or (action == "buy" and sentiment == "flat"):
            # 平仓操作
            logger.info("执行平仓操作")
            do_close_position()
        else:
            logger.warning(f"未识别的交易信号组合: action={action}, position={sentiment}")
        
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        logger.error(f"处理webhook时出错: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("启动成功，当前北京时间：%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    app.run(host='0.0.0.0', port=80, debug=True)
