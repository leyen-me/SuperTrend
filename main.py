from longport.openapi import Config, QuoteContext, TradeContext, OrderType, OrderSide, TimeInForceType, OutsideRTH
import logging
from decimal import Decimal
from flask import Flask, request, jsonify
import datetime

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
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        webhook_data = request.json
        logger.info(f"收到TradingView信号=======>")
        logger.info(f"{webhook_data}")
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        logger.error(f"处理webhook时出错: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    logger.info("启动成功，当前北京时间：%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    app.run(host='0.0.0.0', port=80, debug=True)
