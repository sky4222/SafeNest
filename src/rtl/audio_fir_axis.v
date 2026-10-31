// 16 kHz mono signed PCM16 carried in the low 16 bits of 32-bit AXI words.
// One output for every input. TLAST is propagated; it does NOT clear history.
// Reset between independent recordings, keep history across DMA chunks.
module audio_fir_axis (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK", X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF S_AXIS:M_AXIS, ASSOCIATED_RESET aresetn" *)
    input wire aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST", X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input wire aresetn,
    input wire bypass,
    input wire soft_reset,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TDATA" *) input wire [31:0] s_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TKEEP" *) input wire [3:0] s_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TLAST" *) input wire s_axis_tlast,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TVALID" *) input wire s_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TREADY" *) output wire s_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TDATA" *) output reg [31:0] m_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TKEEP" *) output wire [3:0] m_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TLAST" *) output reg m_axis_tlast,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TVALID" *) output wire m_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TREADY" *) input wire m_axis_tready
);
    localparam TAPS = 257;
    localparam INIT=0, IDLE=1, READ=2, MUL=3, MAC=4, OUT=5;
    reg [2:0] state;
    reg [8:0] clear_index, write_ptr, read_ptr, tap_index;
    (* ram_style = "block" *) reg signed [15:0] history [0:TAPS-1];
    reg signed [15:0] sample_reg, coeff_reg;
    (* use_dsp = "yes" *) reg signed [31:0] product;
    reg signed [47:0] accumulator;
    wire signed [47:0] total = accumulator + {{16{product[31]}}, product};
    reg saved_last;
    `include "fir_coeffs.vh"

    function [31:0] quantize;
        input signed [47:0] value;
        reg signed [47:0] rounded;
        reg signed [15:0] pcm;
        begin
            rounded = (value + 48'sd16384) >>> 15;
            if (rounded > 32767) pcm = 16'sd32767;
            else if (rounded < -32768) pcm = -16'sd32768;
            else pcm = rounded[15:0];
            quantize = {{16{pcm[15]}}, pcm};
        end
    endfunction

    assign s_axis_tready = (state == IDLE) && aresetn && !soft_reset;
    assign m_axis_tvalid = (state == OUT) && aresetn && !soft_reset;
    assign m_axis_tkeep = 4'hf;
    always @(posedge aclk) begin
        if (!aresetn || soft_reset) begin
            state <= INIT;
            clear_index <= 0;
            write_ptr <= 0;
            read_ptr <= 0;
            tap_index <= 0;
            accumulator <= 0;
            sample_reg <= 0;
            coeff_reg <= 0;
            product <= 0;
            saved_last <= 0;
            m_axis_tdata <= 0;
            m_axis_tlast <= 0;
        end else begin
            case (state)
                INIT: begin
                    history[clear_index] <= 0;
                    if (clear_index == TAPS-1) state <= IDLE;
                    else clear_index <= clear_index + 1'b1;
                end
                IDLE: if (s_axis_tvalid) begin
                    saved_last <= s_axis_tlast;
                    if (bypass) begin
                        m_axis_tdata <= {{16{s_axis_tdata[15]}}, s_axis_tdata[15:0]};
                        m_axis_tlast <= s_axis_tlast;
                        state <= OUT;
                    end else begin
                        history[write_ptr] <= s_axis_tdata[15:0];
                        read_ptr <= write_ptr;
                        tap_index <= 0;
                        accumulator <= 0;
                        state <= READ;
                    end
                end
                READ: begin
                    sample_reg <= history[read_ptr];
                    coeff_reg <= coefficient(tap_index);
                    state <= MUL;
                end
                MUL: begin
                    product <= sample_reg * coeff_reg;
                    state <= MAC;
                end
                MAC: begin
                    if (tap_index == TAPS-1) begin
                        m_axis_tdata <= quantize(total);
                        m_axis_tlast <= saved_last;
                        write_ptr <= (write_ptr == TAPS-1) ? 0 : write_ptr + 1'b1;
                        state <= OUT;
                    end else begin
                        accumulator <= total;
                        tap_index <= tap_index + 1'b1;
                        read_ptr <= (read_ptr == 0) ? TAPS-1 : read_ptr - 1'b1;
                        state <= READ;
                    end
                end
                OUT: if (m_axis_tready) state <= IDLE;
                default: state <= INIT;
            endcase
        end
    end
endmodule
