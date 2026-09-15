#property strict
#property version   "1.23"
#property description "FX2Active local bridge for macOS MetaTrader 5"
#property description "Attach this EA to one chart and keep Algo Trading enabled."

#define FX2ACTIVE_PROTOCOL_VERSION 2
#define FX2ACTIVE_ORDER_PROTOCOL 1
#define FX2ACTIVE_MAGIC 26091501

string BridgeVersion = "1.23";
string BridgeFolder = "FX2Active";
string SnapshotFile = "FX2Active\\snapshot.json";
string SnapshotTempFile = "FX2Active\\snapshot.tmp";
string RequestedSymbolFile = "FX2Active\\requested_symbol.txt";
string OrderCommandFile = "FX2Active\\order_command.txt";
string OrderResultFile = "FX2Active\\order_result.json";
string OrderResultTempFile = "FX2Active\\order_result.tmp";
string LastCommandFile = "FX2Active\\last_command.txt";

string JsonBool(bool value)
  {
   return value ? "true" : "false";
  }

string JsonEscape(string value)
  {
   StringReplace(value,"\\","\\\\");
   StringReplace(value,"\"","\\\"");
   StringReplace(value,"\r","\\r");
   StringReplace(value,"\n","\\n");
   return value;
  }

string JsonString(string value)
  {
   return "\"" + JsonEscape(value) + "\"";
  }

string ReadWholeText(string filename)
  {
   int handle=FileOpen(filename,
                       FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ|FILE_SHARE_WRITE,
                       0,CP_UTF8);
   if(handle==INVALID_HANDLE)
      return "";

   string text="";
   while(!FileIsEnding(handle))
     {
      string line=FileReadString(handle);
      if(StringLen(text)>0)
         text+="\n";
      text+=line;
     }
   FileClose(handle);
   return text;
  }

bool WriteWholeText(string filename,string text)
  {
   int handle=FileOpen(filename,
                       FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ,
                       0,CP_UTF8);
   if(handle==INVALID_HANDLE)
      return false;
   FileWriteString(handle,text);
   FileFlush(handle);
   FileClose(handle);
   return true;
  }

string CommandValue(string text,string key)
  {
   string needle=key+"=";
   int start=StringFind(text,needle);
   if(start<0)
      return "";
   start+=StringLen(needle);
   int finish=StringFind(text,"\n",start);
   string value=(finish<0 ? StringSubstr(text,start) : StringSubstr(text,start,finish-start));
   StringTrimLeft(value);
   StringTrimRight(value);
   return value;
  }

string ReadRequestedSymbol()
  {
   string requested=ReadWholeText(RequestedSymbolFile);
   StringTrimLeft(requested);
   StringTrimRight(requested);
   if(StringLen(requested)==0)
      return _Symbol;
   return requested;
  }

int CountFX2ActivePositions()
  {
   int count=0;
   for(int i=0;i<PositionsTotal();i++)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC)==FX2ACTIVE_MAGIC)
         count++;
     }
   return count;
  }

int CountFX2ActiveOrders()
  {
   int count=0;
   for(int i=0;i<OrdersTotal();i++)
     {
      ulong ticket=OrderGetTicket(i);
      if(ticket==0)
         continue;
      if((long)OrderGetInteger(ORDER_MAGIC)==FX2ACTIVE_MAGIC)
         count++;
     }
   return count;
  }

string BuildRatesJson(string symbol)
  {
   MqlRates rates[];
   ArraySetAsSeries(rates,false);
   int copied=CopyRates(symbol,PERIOD_M15,0,300,rates);
   if(copied<=0)
      return "[]";

   string result="[";
   for(int i=0;i<copied;i++)
     {
      if(i>0)
         result+=",";
      result+="["+
              IntegerToString((long)rates[i].time)+","+
              DoubleToString(rates[i].open,10)+","+
              DoubleToString(rates[i].high,10)+","+
              DoubleToString(rates[i].low,10)+","+
              DoubleToString(rates[i].close,10)+"]";
     }
   result+="]";
   return result;
  }

string CloseReasonName(long reason)
  {
   if(reason==DEAL_REASON_SL)
      return "Stop Loss";
   if(reason==DEAL_REASON_TP)
      return "Take Profit";
   if(reason==DEAL_REASON_EXPERT)
      return "Expert";
   if(reason==DEAL_REASON_CLIENT)
      return "Terminal";
   if(reason==DEAL_REASON_MOBILE)
      return "Mobile";
   if(reason==DEAL_REASON_WEB)
      return "Web";
   return "Closed";
  }

string BuildClosedDealsJson()
  {
   datetime to_time=TimeCurrent();
   datetime from_time=to_time-(30*24*60*60);
   if(!HistorySelect(from_time,to_time))
      return "[]";

   int total=HistoryDealsTotal();
   string result="[";
   int emitted=0;

   for(int i=total-1;i>=0 && emitted<100;i--)
     {
      ulong ticket=HistoryDealGetTicket(i);
      if(ticket==0)
         continue;
      if((long)HistoryDealGetInteger(ticket,DEAL_MAGIC)!=FX2ACTIVE_MAGIC)
         continue;

      long entry=HistoryDealGetInteger(ticket,DEAL_ENTRY);
      if(entry!=DEAL_ENTRY_OUT && entry!=DEAL_ENTRY_OUT_BY && entry!=DEAL_ENTRY_INOUT)
         continue;

      long type=HistoryDealGetInteger(ticket,DEAL_TYPE);
      string side="";
      if(type==DEAL_TYPE_SELL)
         side="BUY";
      else if(type==DEAL_TYPE_BUY)
         side="SELL";

      double profit=HistoryDealGetDouble(ticket,DEAL_PROFIT);
      double commission=HistoryDealGetDouble(ticket,DEAL_COMMISSION);
      double swap=HistoryDealGetDouble(ticket,DEAL_SWAP);
      double fee=HistoryDealGetDouble(ticket,DEAL_FEE);
      double net_profit=profit+commission+swap+fee;
      long reason=HistoryDealGetInteger(ticket,DEAL_REASON);

      if(emitted>0)
         result+=",";
      result+="{";
      result+="\"deal_ticket\":"+IntegerToString((long)ticket)+",";
      result+="\"position_id\":"+IntegerToString(HistoryDealGetInteger(ticket,DEAL_POSITION_ID))+",";
      result+="\"timestamp_utc\":"+IntegerToString(HistoryDealGetInteger(ticket,DEAL_TIME))+",";
      result+="\"symbol\":"+JsonString(HistoryDealGetString(ticket,DEAL_SYMBOL))+",";
      result+="\"side\":"+JsonString(side)+",";
      result+="\"price\":"+DoubleToString(HistoryDealGetDouble(ticket,DEAL_PRICE),10)+",";
      result+="\"volume\":"+DoubleToString(HistoryDealGetDouble(ticket,DEAL_VOLUME),8)+",";
      result+="\"profit\":"+DoubleToString(profit,8)+",";
      result+="\"commission\":"+DoubleToString(commission,8)+",";
      result+="\"swap\":"+DoubleToString(swap,8)+",";
      result+="\"fee\":"+DoubleToString(fee,8)+",";
      result+="\"net_profit\":"+DoubleToString(net_profit,8)+",";
      result+="\"close_reason\":"+JsonString(CloseReasonName(reason));
      result+="}";
      emitted++;
     }

   result+="]";
   return result;
  }

ENUM_ORDER_TYPE_FILLING ResolveFillingMode(string symbol,bool pending)
  {
   if(pending)
      return ORDER_FILLING_RETURN;

   long filling=0;
   long execution=0;
   SymbolInfoInteger(symbol,SYMBOL_FILLING_MODE,filling);
   SymbolInfoInteger(symbol,SYMBOL_TRADE_EXEMODE,execution);

   if((filling & SYMBOL_FILLING_IOC)==SYMBOL_FILLING_IOC)
      return ORDER_FILLING_IOC;
   if((filling & SYMBOL_FILLING_FOK)==SYMBOL_FILLING_FOK)
      return ORDER_FILLING_FOK;
   if(execution!=SYMBOL_TRADE_EXECUTION_MARKET)
      return ORDER_FILLING_RETURN;
   return ORDER_FILLING_FOK;
  }

bool IsAcceptedRetcode(uint retcode)
  {
   return retcode==TRADE_RETCODE_PLACED ||
          retcode==TRADE_RETCODE_DONE ||
          retcode==TRADE_RETCODE_DONE_PARTIAL;
  }

void PublishOrderResult(string command_id,
                        bool ok,
                        string status,
                        string message,
                        uint retcode,
                        ulong order_ticket,
                        ulong deal_ticket,
                        double volume,
                        double price)
  {
   string json="{";
   json+="\"protocol\":"+IntegerToString(FX2ACTIVE_ORDER_PROTOCOL)+",";
   json+="\"command_id\":"+JsonString(command_id)+",";
   json+="\"ok\":"+JsonBool(ok)+",";
   json+="\"status\":"+JsonString(status)+",";
   json+="\"message\":"+JsonString(message)+",";
   json+="\"retcode\":"+IntegerToString((long)retcode)+",";
   json+="\"order\":"+IntegerToString((long)order_ticket)+",";
   json+="\"deal\":"+IntegerToString((long)deal_ticket)+",";
   json+="\"volume\":"+DoubleToString(volume,8)+",";
   json+="\"price\":"+DoubleToString(price,10)+",";
   json+="\"timestamp_utc\":"+IntegerToString((long)TimeGMT());
   json+="}";

   if(!WriteWholeText(OrderResultTempFile,json))
     {
      Print("FX2Active bridge could not write order result. Error ",GetLastError());
      return;
     }
   ResetLastError();
   if(!FileMove(OrderResultTempFile,FILE_COMMON,OrderResultFile,FILE_COMMON|FILE_REWRITE))
      Print("FX2Active bridge could not publish order result. Error ",GetLastError());
  }

void BlockCommand(string command_id,string message,uint retcode=0)
  {
   PublishOrderResult(command_id,false,"blocked",message,retcode,0,0,0.0,0.0);
   FileDelete(OrderCommandFile,FILE_COMMON);
  }

void ProcessTradeCommand()
  {
   if(!FileIsExist(OrderCommandFile,FILE_COMMON))
      return;

   string text=ReadWholeText(OrderCommandFile);
   if(StringLen(text)==0)
      return;

   int protocol=(int)StringToInteger(CommandValue(text,"protocol"));
   string command_id=CommandValue(text,"command_id");
   if(protocol!=FX2ACTIVE_ORDER_PROTOCOL || StringLen(command_id)==0)
     {
      BlockCommand(command_id,"Invalid FX2Active order command protocol.");
      return;
     }

   string last_id=ReadWholeText(LastCommandFile);
   StringTrimLeft(last_id);
   StringTrimRight(last_id);
   if(last_id==command_id)
     {
      FileDelete(OrderCommandFile,FILE_COMMON);
      return;
     }

   if(!(bool)TerminalInfoInteger(TERMINAL_CONNECTED))
     {
      BlockCommand(command_id,"MT5 terminal is not connected.");
      return;
     }
   if(!(bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) ||
      !(bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) ||
      !(bool)AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
     {
      BlockCommand(command_id,"MT5 Algo Trading/account Expert Advisor trading permission is disabled.");
      return;
     }

   bool allow_live=(StringToInteger(CommandValue(text,"allow_live"))==1);
   long account_mode=AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(account_mode==ACCOUNT_TRADE_MODE_REAL && !allow_live)
     {
      BlockCommand(command_id,"Real/live account execution is not armed in FX2Active.");
      return;
     }

   long magic=(long)StringToInteger(CommandValue(text,"magic"));
   if(magic!=FX2ACTIVE_MAGIC)
     {
      BlockCommand(command_id,"Invalid FX2Active magic number.");
      return;
     }

   string symbol=CommandValue(text,"symbol");
   string side=CommandValue(text,"side");
   string mode=CommandValue(text,"mode");
   double volume=StringToDouble(CommandValue(text,"volume"));
   double planned_entry=StringToDouble(CommandValue(text,"entry"));
   double sl=StringToDouble(CommandValue(text,"sl"));
   double tp=StringToDouble(CommandValue(text,"tp"));
   int deviation=(int)StringToInteger(CommandValue(text,"deviation"));
   double max_spread_pips=StringToDouble(CommandValue(text,"max_spread_pips"));
   int max_exposure=(int)StringToInteger(CommandValue(text,"max_exposure"));

   if((side!="BUY" && side!="SELL") || (mode!="MARKET" && mode!="PENDING"))
     {
      BlockCommand(command_id,"Invalid FX2Active order side or mode.");
      return;
     }
   if(volume<=0.0 || planned_entry<=0.0 || sl<=0.0 || tp<=0.0)
     {
      BlockCommand(command_id,"Invalid FX2Active order prices or volume.");
      return;
     }
   if(max_exposure<=0)
     {
      BlockCommand(command_id,"Invalid FX2Active maximum exposure setting.");
      return;
     }

   int current_exposure=CountFX2ActivePositions()+CountFX2ActiveOrders();
   if(current_exposure>=max_exposure)
     {
      BlockCommand(command_id,"FX2Active position/order limit reached.");
      return;
     }

   if(!SymbolSelect(symbol,true))
     {
      BlockCommand(command_id,"MT5 could not select the requested symbol.");
      return;
     }

   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick) || tick.bid<=0.0 || tick.ask<=0.0 || tick.ask<tick.bid)
     {
      BlockCommand(command_id,"MT5 returned no valid Bid/Ask for the symbol.");
      return;
     }

   double point=0.0;
   long digits=0;
   long stops_level=0;
   double volume_min=0.0;
   double volume_max=0.0;
   double volume_step=0.0;
   SymbolInfoDouble(symbol,SYMBOL_POINT,point);
   SymbolInfoInteger(symbol,SYMBOL_DIGITS,digits);
   SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL,stops_level);
   SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN,volume_min);
   SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX,volume_max);
   SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP,volume_step);
   if(point<=0.0 || volume_min<=0.0 || volume_max<volume_min || volume_step<=0.0)
     {
      BlockCommand(command_id,"Broker returned invalid symbol trading limits.");
      return;
     }
   if(volume<volume_min-1e-12 || volume>volume_max+1e-12)
     {
      BlockCommand(command_id,"FX2Active volume is outside the broker limits.");
      return;
     }
   double volume_units=volume/volume_step;
   if(MathAbs(volume_units-MathRound(volume_units))>1e-7)
     {
      BlockCommand(command_id,"FX2Active volume does not match the broker volume step.");
      return;
     }

   double pip_size=((digits==3 || digits==5) ? point*10.0 : point);
   double spread_pips=(tick.ask-tick.bid)/pip_size;
   if(max_spread_pips>0.0 && spread_pips>max_spread_pips)
     {
      BlockCommand(command_id,"Current spread exceeds the FX2Active limit.");
      return;
     }

   bool pending=(mode=="PENDING");
   ENUM_ORDER_TYPE order_type;
   ENUM_TRADE_REQUEST_ACTIONS action;
   double price=planned_entry;

   if(pending)
     {
      action=TRADE_ACTION_PENDING;
      order_type=(side=="BUY" ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT);
      if(side=="BUY" && price>=tick.ask)
        {
         BlockCommand(command_id,"BUY LIMIT must be below the current Ask.");
         return;
        }
      if(side=="SELL" && price<=tick.bid)
        {
         BlockCommand(command_id,"SELL LIMIT must be above the current Bid.");
         return;
        }
     }
   else
     {
      action=TRADE_ACTION_DEAL;
      order_type=(side=="BUY" ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
      price=(side=="BUY" ? tick.ask : tick.bid);
     }

   price=NormalizeDouble(price,(int)digits);
   sl=NormalizeDouble(sl,(int)digits);
   tp=NormalizeDouble(tp,(int)digits);

   if(side=="BUY" && !(sl<price && price<tp))
     {
      BlockCommand(command_id,"BUY order has invalid SL/entry/TP order.");
      return;
     }
   if(side=="SELL" && !(tp<price && price<sl))
     {
      BlockCommand(command_id,"SELL order has invalid TP/entry/SL order.");
      return;
     }

   double minimum_distance=(double)stops_level*point;
   if(minimum_distance>0.0)
     {
      if(MathAbs(price-sl)+1e-12<minimum_distance || MathAbs(tp-price)+1e-12<minimum_distance)
        {
         BlockCommand(command_id,"SL/TP is inside the broker minimum stop distance.");
         return;
        }
      if(pending)
        {
         double market_distance=(side=="BUY" ? tick.ask-price : price-tick.bid);
         if(market_distance+1e-12<minimum_distance)
           {
            BlockCommand(command_id,"Pending entry is inside the broker minimum distance.");
            return;
           }
        }
     }

   MqlTradeRequest request={};
   MqlTradeCheckResult check={};
   MqlTradeResult result={};
   request.action=action;
   request.magic=FX2ACTIVE_MAGIC;
   request.symbol=symbol;
   request.volume=volume;
   request.type=order_type;
   request.price=price;
   request.sl=sl;
   request.tp=tp;
   request.deviation=(ulong)MathMax(0,deviation);
   request.type_time=ORDER_TIME_GTC;
   request.type_filling=ResolveFillingMode(symbol,pending);
   request.comment="FX2Active";

   ResetLastError();
   if(!OrderCheck(request,check) || check.retcode!=0)
     {
      string check_message="MT5 OrderCheck rejected the FX2Active order: "+check.comment;
      BlockCommand(command_id,check_message,check.retcode);
      return;
     }

   // Persist the command id only after every retryable pre-check has passed.
   // From this point on, a crash must never cause this order to be submitted twice.
   if(!WriteWholeText(LastCommandFile,command_id+"\n"))
     {
      BlockCommand(command_id,"Could not persist FX2Active duplicate guard.");
      return;
     }

   ResetLastError();
   bool sent=OrderSend(request,result);
   bool accepted=sent && IsAcceptedRetcode(result.retcode);
   string status="rejected";
   if(accepted)
     {
      status=(result.retcode==TRADE_RETCODE_PLACED ? "placed" :
              (result.retcode==TRADE_RETCODE_DONE_PARTIAL ? "partial" : "filled"));
     }

   string message=result.comment;
   if(StringLen(message)==0)
      message=(accepted ? "MT5 accepted the FX2Active order." : "MT5 rejected the FX2Active order.");

   PublishOrderResult(command_id,accepted,status,message,result.retcode,
                      result.order,result.deal,result.volume,result.price);
   FileDelete(OrderCommandFile,FILE_COMMON);
  }

void WriteSnapshot()
  {
   FolderCreate(BridgeFolder,FILE_COMMON);

   string symbol=ReadRequestedSymbol();
   ResetLastError();
   bool selected=SymbolSelect(symbol,true);

   double point=0.0;
   long digits=0;
   double volume_min=0.0;
   double volume_max=0.0;
   double volume_step=0.0;
   double tick_size=0.0;
   double tick_value_loss=0.0;
   double bid=0.0;
   double ask=0.0;
   long stops_level=0;
   long filling_mode=0;
   long trade_exemode=0;

   if(selected)
     {
      SymbolInfoDouble(symbol,SYMBOL_POINT,point);
      SymbolInfoInteger(symbol,SYMBOL_DIGITS,digits);
      SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN,volume_min);
      SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX,volume_max);
      SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP,volume_step);
      SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE,tick_size);
      SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE_LOSS,tick_value_loss);
      SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL,stops_level);
      SymbolInfoInteger(symbol,SYMBOL_FILLING_MODE,filling_mode);
      SymbolInfoInteger(symbol,SYMBOL_TRADE_EXEMODE,trade_exemode);
      MqlTick tick;
      if(SymbolInfoTick(symbol,tick))
        {
         bid=tick.bid;
         ask=tick.ask;
        }
     }

   long heartbeat=(long)TimeGMT();
   string json="{";
   json+="\"protocol_version\":"+IntegerToString(FX2ACTIVE_PROTOCOL_VERSION)+",";
   json+="\"bridge_version\":"+JsonString(BridgeVersion)+",";
   json+="\"execution_bridge\":true,";
   json+="\"heartbeat\":"+IntegerToString(heartbeat)+",";
   json+="\"heartbeat_utc\":"+IntegerToString(heartbeat)+",";
   json+="\"terminal\":{";
   json+="\"connected\":"+JsonBool((bool)TerminalInfoInteger(TERMINAL_CONNECTED))+",";
   json+="\"trade_allowed\":"+JsonBool((bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))+",";
   json+="\"build\":"+IntegerToString(TerminalInfoInteger(TERMINAL_BUILD))+"},";
   json+="\"account\":{";
   json+="\"login\":"+JsonString(IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)))+",";
   json+="\"server\":"+JsonString(AccountInfoString(ACCOUNT_SERVER))+",";
   json+="\"currency\":"+JsonString(AccountInfoString(ACCOUNT_CURRENCY))+",";
   json+="\"balance\":"+DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2)+",";
   json+="\"equity\":"+DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2)+",";
   json+="\"trade_mode\":"+IntegerToString(AccountInfoInteger(ACCOUNT_TRADE_MODE))+",";
   json+="\"trade_allowed\":"+JsonBool((bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))+",";
   json+="\"trade_expert\":"+JsonBool((bool)AccountInfoInteger(ACCOUNT_TRADE_EXPERT))+"},";
   json+="\"open_positions\":"+IntegerToString(PositionsTotal())+",";
   json+="\"fx2active_open_positions\":"+IntegerToString(CountFX2ActivePositions())+",";
   json+="\"fx2active_pending_orders\":"+IntegerToString(CountFX2ActiveOrders())+",";
   json+="\"symbol\":{";
   json+="\"name\":"+JsonString(symbol)+",";
   json+="\"selected\":"+JsonBool(selected)+",";
   json+="\"point\":"+DoubleToString(point,10)+",";
   json+="\"digits\":"+IntegerToString(digits)+",";
   json+="\"bid\":"+DoubleToString(bid,10)+",";
   json+="\"ask\":"+DoubleToString(ask,10)+",";
   json+="\"trade_stops_level\":"+IntegerToString(stops_level)+",";
   json+="\"filling_mode\":"+IntegerToString(filling_mode)+",";
   json+="\"trade_exemode\":"+IntegerToString(trade_exemode)+",";
   json+="\"volume_min\":"+DoubleToString(volume_min,8)+",";
   json+="\"volume_max\":"+DoubleToString(volume_max,8)+",";
   json+="\"volume_step\":"+DoubleToString(volume_step,8)+",";
   json+="\"trade_tick_size\":"+DoubleToString(tick_size,10)+",";
   json+="\"trade_tick_value_loss\":"+DoubleToString(tick_value_loss,10)+"},";
   json+="\"closed_trades\":"+BuildClosedDealsJson()+",";
   json+="\"rates\":"+(selected ? BuildRatesJson(symbol) : "[]");
   json+="}";

   int handle=FileOpen(SnapshotTempFile,
                       FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ,
                       0,CP_UTF8);
   if(handle==INVALID_HANDLE)
     {
      Print("FX2Active bridge could not open temporary snapshot file. Error ",GetLastError());
      return;
     }

   FileWriteString(handle,json);
   FileFlush(handle);
   FileClose(handle);

   ResetLastError();
   if(!FileMove(SnapshotTempFile,FILE_COMMON,SnapshotFile,FILE_COMMON|FILE_REWRITE))
      Print("FX2Active bridge could not publish snapshot file. Error ",GetLastError());
  }

int OnInit()
  {
   if(!EventSetTimer(1))
     {
      Print("FX2Active bridge could not start its timer. Error ",GetLastError());
      return INIT_FAILED;
     }

   WriteSnapshot();
   ProcessTradeCommand();
   Print("FX2Active bridge v1.23 started. Keep this EA attached to one chart.");
   return INIT_SUCCEEDED;
  }

void OnTimer()
  {
   ProcessTradeCommand();
   WriteSnapshot();
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }
