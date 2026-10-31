`timescale 1ns/1ps
module tb_audio_fir;
    reg clk=0; always #5 clk=~clk;
    reg resetn=0, bypass=0, soft_reset=0;
    reg [31:0] din=0; reg valid=0,last=0,ready=0;
    wire in_ready,out_valid,out_last; wire [31:0] dout; wire [3:0] keep;
    reg [31:0] stimulus[0:1023], expected[0:1023];
    integer received=0, phase=0;
    reg [31:0] random_state=32'hace12458;
    reg stalled=0; reg [31:0] held_data; reg held_last;
    audio_fir_axis dut(.aclk(clk),.aresetn(resetn),.bypass(bypass),.soft_reset(soft_reset),
        .s_axis_tdata(din),.s_axis_tkeep(4'hf),.s_axis_tlast(last),
        .s_axis_tvalid(valid),.s_axis_tready(in_ready),.m_axis_tdata(dout),
        .m_axis_tkeep(keep),.m_axis_tlast(out_last),.m_axis_tvalid(out_valid),.m_axis_tready(ready));
    // Repeatable backpressure, including stalls while output is valid.
    always @(negedge clk) begin
        random_state = {random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        ready = random_state[0] | random_state[3];
    end
    always @(posedge clk) begin
        if (!resetn || soft_reset) stalled <= 0;
        else begin
            if (stalled && (!out_valid || dout !== held_data || out_last !== held_last))
                $fatal(1,"AXIS output changed while stalled");
            stalled <= out_valid && !ready;
            held_data <= dout; held_last <= out_last;
            if (out_valid && ready) begin
                if (received >= 1024) $fatal(1,"Extra output");
                if (dout !== ((phase==0) ? stimulus[received] : expected[received]))
                    $fatal(1,"Mismatch phase=%0d sample=%0d actual=%h expected=%h",phase,received,dout,expected[received]);
                if (out_last !== ((received==511)||(received==1023))) $fatal(1,"TLAST mismatch");
                if (keep !== 4'hf) $fatal(1,"TKEEP mismatch");
                received = received+1;
            end
        end
    end
    task send_frame;
        integer i;
        begin
            for (i=0;i<1024;i=i+1) begin
                repeat (i%3) @(negedge clk);
                @(negedge clk); din=stimulus[i]; last=(i==511)||(i==1023); valid=1;
                @(posedge clk); while (!in_ready) @(posedge clk);
                @(negedge clk); valid=0;
            end
            wait(received==1024);
            repeat(5) @(negedge clk);
        end
    endtask
    initial begin
        $readmemh("input.mem",stimulus); $readmemh("expected.mem",expected);
        repeat(5) @(negedge clk); resetn=1; bypass=1;
        send_frame();
        soft_reset=1; repeat(5) @(negedge clk);
        phase=1; received=0; bypass=0; soft_reset=0;
        send_frame();
        // Independent recording must begin with cleared history.
        soft_reset=1; repeat(5) @(negedge clk);
        received=0; soft_reset=0;
        send_frame();
        $display("PASS: bypass, FIR, reset, packet continuity, backpressure"); $finish;
    end
    initial begin #30000000; $fatal(1,"Simulation timed out"); end
endmodule
