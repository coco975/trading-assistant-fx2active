#property strict
#property version   "1.10"
#property description "FX2Active local bridge for macOS MetaTrader 5"
#property description "Attach this EA to one chart and keep Algo Trading enabled."

#define FX2ACTIVE_PROTOCOL_VERSION 2

string BridgeVersion = "1.10";
string BridgeFolder = "FX2Active";
string SnapshotFile = "FX2Active\\snapshot.json";
string SnapshotTempFile = "FX2Active\\snapshot.tmp";
string RequestedSymbolFile = "FX2Active\\requested_symbol.txt";

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

string ReadRequestedSymbol()
  {
   int handle=FileOpen(RequestedSymbolFile,
                       FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ|FILE_SHARE_WRITE,
                       0,CP_UTF8);
   if(handle==INVALID_HANDLE)
      return _Symbol;

   string requested=FileReadString(handle);
   FileClose(handle);
   StringTrimLeft(requested);
   StringTrimRight(requested);
   if(StringLen(requested)==0)
      return _Symbol;
   return requested;
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

   if(selected)
     {
      SymbolInfoDouble(symbol,SYMBOL_POINT,point);
      SymbolInfoInteger(symbol,SYMBOL_DIGITS,digits);
      SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN,volume_min);
      SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX,volume_max);
      SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP,volume_step);
      SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE,tick_size);
      SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE_LOSS,tick_value_loss);
     }

   long heartbeat=(long)TimeGMT();
   string json="{";
   json+="\"protocol_version\":"+IntegerToString(FX2ACTIVE_PROTOCOL_VERSION)+",";
   json+="\"bridge_version\":"+JsonString(BridgeVersion)+",";
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
   json+="\"trade_allowed\":"+JsonBool((bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))+"},";
   json+="\"open_positions\":"+IntegerToString(PositionsTotal())+",";
   json+="\"symbol\":{";
   json+="\"name\":"+JsonString(symbol)+",";
   json+="\"selected\":"+JsonBool(selected)+",";
   json+="\"point\":"+DoubleToString(point,10)+",";
   json+="\"digits\":"+IntegerToString(digits)+",";
   json+="\"volume_min\":"+DoubleToString(volume_min,8)+",";
   json+="\"volume_max\":"+DoubleToString(volume_max,8)+",";
   json+="\"volume_step\":"+DoubleToString(volume_step,8)+",";
   json+="\"trade_tick_size\":"+DoubleToString(tick_size,10)+",";
   json+="\"trade_tick_value_loss\":"+DoubleToString(tick_value_loss,10)+"},";
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
     {
      Print("FX2Active bridge could not publish snapshot file. Error ",GetLastError());
      return;
     }
  }

int OnInit()
  {
   if(!EventSetTimer(1))
     {
      Print("FX2Active bridge could not start its timer. Error ",GetLastError());
      return INIT_FAILED;
     }

   WriteSnapshot();
   Print("FX2Active bridge started. Keep this EA attached to one chart.");
   return INIT_SUCCEEDED;
  }

void OnTimer()
  {
   WriteSnapshot();
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }
