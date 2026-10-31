`timescale 1ns/1ps
// PS sends class IDs only. Rolling score, threshold and timers are PL logic.
// command: [1:0] class, [8] request toggle, [9] enable,
//          [10] clear, [12] mute physical buzzer (timers still operate).
// status: [3:0] sum, [5:4] valid count, [7:6] last class,
// [8] active, [9] cooldown, [10] last event triggered alarm,
// [11] accepted toggle, [12] enabled, [13] mute, [31:16] event counter.
module alarm_score #(
    parameter integer CLK_HZ = 100000000,
    parameter integer BEEP_SECONDS = 2,
    parameter integer COOLDOWN_SECONDS = 10,
    parameter integer STALE_SECONDS = 15
)(
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK",
       X_INTERFACE_PARAMETER = "ASSOCIATED_RESET aresetn, FREQ_HZ 100000000" *)
    input wire aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST",
       X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input wire aresetn,
    input wire [31:0] command,
    output wire [31:0] status,
    output wire buzzer_n
);
    localparam integer BEEP_TICKS = CLK_HZ * BEEP_SECONDS;
    localparam integer COOL_TICKS = CLK_HZ * COOLDOWN_SECONDS;
    localparam integer STALE_TICKS = CLK_HZ * STALE_SECONDS;
    reg [1:0] previous1, previous2, count, last_class;
    reg [3:0] sum;
    reg accepted, last_trigger;
    reg [15:0] event_count;
    reg [31:0] beep_left, cool_left, idle_ticks;
    wire [1:0] weight = command[1:0] == 2 ? 2'd3 :
                        command[1:0] == 1 ? 2'd2 : 2'd0;
    wire stale = idle_ticks >= STALE_TICKS;
    wire [3:0] next_sum = {2'b0,weight} +
                         (stale ? 4'd0 : {2'b0,previous1}) +
                         (stale ? 4'd0 : {2'b0,previous2});
    wire active = beep_left != 0;
    wire cooling = cool_left != 0;
    // Disable, clear and reset always force physical output high (silent).
    assign buzzer_n = !(aresetn && command[9] && !command[10] &&
                        !command[12] && active);
    assign status = {event_count, 2'b0, command[12], command[9],
                     accepted, last_trigger, cooling, active,
                     last_class, count, sum};

    always @(posedge aclk) begin
        if (!aresetn) begin
            previous1 <= 0; previous2 <= 0; count <= 0; last_class <= 0;
            sum <= 0; accepted <= 0; last_trigger <= 0; event_count <= 0;
            beep_left <= 0; cool_left <= 0; idle_ticks <= 0;
        end else if (!command[9] || command[10]) begin
            previous1 <= 0; previous2 <= 0; count <= 0; last_class <= 0;
            sum <= 0; accepted <= command[8]; last_trigger <= 0;
            event_count <= 0; beep_left <= 0; cool_left <= 0; idle_ticks <= 0;
        end else begin
            if (beep_left != 0) begin
                beep_left <= beep_left - 1;
                if (beep_left == 1) cool_left <= COOL_TICKS;
            end else if (cool_left != 0) cool_left <= cool_left - 1;
            if (!stale) idle_ticks <= idle_ticks + 1;
            else begin
                previous1 <= 0; previous2 <= 0; sum <= 0; count <= 0;
                last_trigger <= 0;
            end
            if (command[8] != accepted) begin
                accepted <= command[8]; event_count <= event_count + 1;
                last_class <= command[1:0]; idle_ticks <= 0;
                previous2 <= stale ? 2'd0 : previous1;
                previous1 <= weight; sum <= next_sum;
                count <= stale ? 2'd1 : (count == 3 ? 2'd3 : count + 1'b1);
                last_trigger <= 0;
                if (next_sum >= 4 && beep_left == 0 && cool_left == 0) begin
                    beep_left <= BEEP_TICKS;
                    last_trigger <= 1;
                end
            end
        end
    end
endmodule
