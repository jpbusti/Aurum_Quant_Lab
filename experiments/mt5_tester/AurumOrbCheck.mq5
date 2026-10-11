//+------------------------------------------------------------------+
//| AurumOrbCheck.mq5                                                |
//| Verificación independiente de AURUM Quant Lab: reproduce         |
//| CAND-ORB-NY-v1 en el Strategy Tester de MT5 para comparar        |
//| operación a operación con el motor en Python.                    |
//|                                                                  |
//| SOLO TESTER: si se carga en un gráfico real, se niega a iniciar. |
//| Reglas (docs/STRATEGY_RESEARCH.md), hora del servidor = NY + 7 h:|
//|  - vela M15 de las 16:30 del servidor (09:30 NY)                 |
//|  - a las 16:45: compra si cierre > apertura, venta si <          |
//|  - stop en el extremo opuesto, objetivo 10R desde el cierre       |
//|  - cierre a las 23:00 del servidor (16:00 NY)                    |
//|  - volumen fijo de 0,01 lotes                                     |
//+------------------------------------------------------------------+
#property strict
#include <Trade/Trade.mqh>

input double InpVolume  = 0.01;
input double InpTargetR = 10.0;
input string InpCsvName = "aurum_orb_check.csv";

CTrade   trade;
datetime last_bar = 0;
datetime entry_day = 0;
int      csv = INVALID_HANDLE;

int OnInit()
{
   if(!MQLInfoInteger(MQL_TESTER))
   {
      Print("AurumOrbCheck solo funciona en el Strategy Tester.");
      return(INIT_FAILED);
   }
   trade.SetExpertMagicNumber(20261011);
   csv = FileOpen(InpCsvName, FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(csv == INVALID_HANDLE) return(INIT_FAILED);
   FileWrite(csv, "event", "server_time", "side", "price", "sl", "tp", "volume", "profit", "commission", "swap", "reason");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   if(csv != INVALID_HANDLE) FileClose(csv);
}

int MinuteOfDay(datetime t) { return (int)((t % 86400) / 60); }

void OnTick()
{
   datetime now = TimeCurrent();

   // Cierre por tiempo a las 23:00 del servidor (16:00 NY).
   if(PositionSelect(_Symbol) && MinuteOfDay(now) >= 23 * 60)
      trade.PositionClose(_Symbol);

   datetime bar = iTime(_Symbol, PERIOD_M15, 0);
   if(bar == last_bar) return;
   last_bar = bar;
   if(MinuteOfDay(bar) != 16 * 60 + 45) return;          // nueva vela de las 16:45
   datetime day = bar - (bar % 86400);
   if(day == entry_day || PositionSelect(_Symbol)) return;

   datetime rt = iTime(_Symbol, PERIOD_M15, 1);
   if(rt != bar - 900) return;                             // la vela de rango debe existir
   double o = iOpen(_Symbol, PERIOD_M15, 1), h = iHigh(_Symbol, PERIOD_M15, 1);
   double l = iLow(_Symbol, PERIOD_M15, 1),  c = iClose(_Symbol, PERIOD_M15, 1);
   if(c == o) return;
   entry_day = day;
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   if(c > o)
   {
      double tp = NormalizeDouble(c + InpTargetR * (c - l), digits);
      if(!trade.Buy(InpVolume, _Symbol, 0.0, l, tp, "ORB"))
         FileWrite(csv, "rejected", TimeToString(now, TIME_DATE | TIME_SECONDS), 1, 0, l, tp, InpVolume, 0, 0, 0, trade.ResultRetcodeDescription());
   }
   else
   {
      double tp = NormalizeDouble(c - InpTargetR * (h - c), digits);
      if(!trade.Sell(InpVolume, _Symbol, 0.0, h, tp, "ORB"))
         FileWrite(csv, "rejected", TimeToString(now, TIME_DATE | TIME_SECONDS), -1, 0, h, tp, InpVolume, 0, 0, 0, trade.ResultRetcodeDescription());
   }
}

// Registra cada operación ejecutada (entradas y salidas) con su precio real.
void OnTradeTransaction(const MqlTradeTransaction &tx, const MqlTradeRequest &req, const MqlTradeResult &res)
{
   if(tx.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(!HistoryDealSelect(tx.deal)) return;
   long entry = HistoryDealGetInteger(tx.deal, DEAL_ENTRY);
   long type  = HistoryDealGetInteger(tx.deal, DEAL_TYPE);
   long reason = HistoryDealGetInteger(tx.deal, DEAL_REASON);
   string why = reason == DEAL_REASON_SL ? "sl" : reason == DEAL_REASON_TP ? "tp" : "otro";
   FileWrite(csv, entry == DEAL_ENTRY_IN ? "in" : "out",
             TimeToString((datetime)HistoryDealGetInteger(tx.deal, DEAL_TIME), TIME_DATE | TIME_SECONDS),
             type == DEAL_TYPE_BUY ? 1 : -1,
             DoubleToString(HistoryDealGetDouble(tx.deal, DEAL_PRICE), 2),
             DoubleToString(tx.price_sl, 2), DoubleToString(tx.price_tp, 2),
             DoubleToString(HistoryDealGetDouble(tx.deal, DEAL_VOLUME), 2),
             DoubleToString(HistoryDealGetDouble(tx.deal, DEAL_PROFIT), 2),
             DoubleToString(HistoryDealGetDouble(tx.deal, DEAL_COMMISSION), 2),
             DoubleToString(HistoryDealGetDouble(tx.deal, DEAL_SWAP), 2), why);
}
