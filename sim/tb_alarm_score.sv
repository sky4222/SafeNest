`timescale 1ns/1ps
module tb_alarm_score;
 reg clk=0, resetn=0;
 reg [31:0] command=0;
 wire [31:0] status;
 wire buzzer_n;
 integer a,b,c,d,e,prev1,prev2,expected_sum,events,valid_count;
 reg pulse_check=0;
 time low_started;
 alarm_score #(.CLK_HZ(10),.BEEP_SECONDS(2),.COOLDOWN_SECONDS(10),.STALE_SECONDS(15)) dut
   (.aclk(clk),.aresetn(resetn),.command(command),.status(status),.buzzer_n(buzzer_n));
 always #5 clk=~clk;
 always @(negedge buzzer_n) low_started=$time;
 always @(posedge buzzer_n) if(pulse_check && resetn)
   if($time-low_started != 200) $fatal(1,"Buzzer pulse wrong: %0t",$time-low_started);
 function integer weight(input integer cid);
   weight=cid==2 ? 3 : cid==1 ? 2 : 0;
 endfunction
 task ticks(input integer n);
   repeat(n) @(posedge clk);
   #1;
 endtask
 task clear_window(input bit mute);
   @(negedge clk);command=32'h600 | (mute ? 32'h1000 : 0);
   ticks(2);
   @(negedge clk);command[10]=0;
   ticks(2);
   prev1=0;prev2=0;events=0;valid_count=0;
   if(status[9:0]!==0 || buzzer_n!==1) $fatal(1,"Clear/default silent failed");
 endtask
 task submit(input integer cid);
   expected_sum=weight(cid)+prev1+prev2;
   prev2=prev1;prev1=weight(cid);events=events+1;
   if(valid_count<3) valid_count=valid_count+1;
   @(negedge clk);command[1:0]=cid;command[8]=~command[8];
   ticks(2);
   if(status[3:0]!==expected_sum || status[5:4]!==valid_count ||
      status[31:16]!==events || status[11]!==command[8])
     $fatal(1,"Score/ack mismatch cid=%0d expected=%0d status=%h",cid,expected_sum,status);
 endtask
 initial begin
   ticks(3);resetn=1;ticks(2);
   if(buzzer_n!==1) $fatal(1,"Reset must be silent");
   // Exhaustive five-event class sequences, including rolling eviction.
   for(a=0;a<4;a=a+1)for(b=0;b<4;b=b+1)for(c=0;c<4;c=c+1)
   for(d=0;d<4;d=d+1)for(e=0;e<4;e=e+1)begin
     clear_window(1);submit(a);submit(b);submit(c);submit(d);submit(e);
     if(buzzer_n!==1) $fatal(1,"Mute failed");
   end
   $display("PASS: 1024 exhaustive five-event sequences, rolling score, count, acknowledgement, mute");
   clear_window(0);submit(2);
   if(status[10] || !buzzer_n) $fatal(1,"Single scream must not alarm");
   submit(0);submit(0);submit(0);
   if(status[3:0]!=0) $fatal(1,"Old scream not evicted");
   clear_window(0);submit(1);
   if(status[10]) $fatal(1,"Single impact must not alarm");
   pulse_check=1;submit(1);
   if(!status[10] || buzzer_n!==0 || status[3:0]!=4) $fatal(1,"Two impacts must alarm at exactly 4");
   // Held command is not a new observation.
   ticks(3);if(status[31:16]!=2) $fatal(1,"Duplicate submission");
   ticks(20);
   if(status[8] || !status[9] || !buzzer_n) $fatal(1,"Beep/cooldown transition failed");
   submit(2);
   if(status[10]) $fatal(1,"Cooldown must suppress alarm");
   ticks(105);submit(2);
   if(!status[10] || buzzer_n) $fatal(1,"Rearm after cooldown failed");
   ticks(22);pulse_check=0;
   // A stale window expires without PS calls; a new scream is isolated.
   ticks(151);prev1=0;prev2=0;valid_count=0;
   if(status[3:0]!=0 || status[5:4]!=0) $fatal(1,"Stale window not cleared");
   submit(2);
   if(status[10]) $fatal(1,"Expired evidence caused alarm");
   clear_window(0);submit(2);submit(1);
   if(!status[10] || status[3:0]!=5 || buzzer_n) $fatal(1,"Scream plus impact failed");
   @(negedge clk);command[9]=0;
   #1;if(buzzer_n!==1) $fatal(1,"Disarm must immediately silence");
   ticks(2);if(status[3:0]!=0 || status[8]) $fatal(1,"Disarm must clear state");
   clear_window(0);submit(2);submit(2);
   resetn=0;#1;if(buzzer_n!==1) $fatal(1,"Reset while ringing must silence");
   ticks(2);if(status[3:0]!=0) $fatal(1,"Reset state failed");
   $display("PASS: threshold, single-event suppression, eviction, exact beep duration, cooldown, stale expiry, disable and reset");
   $finish;
 end
 initial begin #10000000;$fatal(1,"Watchdog timeout");end
endmodule
