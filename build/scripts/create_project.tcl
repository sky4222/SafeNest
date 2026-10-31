# Fresh Vivado 2023.1: source build/scripts/create_project.tcl
set root [file normalize [file join [file dirname [info script]] ../..]]
if {[version -short] ne "2023.1"} {error "This integration script targets Vivado 2023.1, not 2017.4."}
if {[llength [get_projects -quiet]]} {error "Close the current project first; this script creates a separate project."}
set build [file join $root build]
if {[file exists [file join $build safenest_audio.xpr]]} {error "Project already exists: open build/safenest_audio.xpr instead."}
set_param board.repoPaths [list [file join $root src board_files]]
set boards [get_board_parts -quiet *:pynq-z2:part0:*]
if {![llength $boards]} {error "PYNQ-Z2 board files not found in board_files/"}
create_project safenest_audio $build -part xc7z020clg400-1
set_property board_part [lindex $boards end] [current_project]
set_property target_language Verilog [current_project]
set_property ip_repo_paths [list [file join $root src ip]] [current_project]
update_ip_catalog
add_files [list [file join $root src rtl audio_fir_axis.v] [file join $root src rtl fir_coeffs.vh] [file join $root src rtl alarm_score.v]]
set_property include_dirs [list [file join $root src rtl]] [get_filesets sources_1]
set_property file_type {Verilog Header} [get_files fir_coeffs.vh]
create_bd_design system
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} [get_bd_cells ps7]
set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_USE_S_AXI_HP0 {1} CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100} CONFIG.PCW_I2C1_PERIPHERAL_ENABLE {1} CONFIG.PCW_I2C1_I2C1_IO {EMIO}] [get_bd_cells ps7]
# Official PYNQ codec IP retained at its Linux UIO physical address.
create_bd_cell -type ip -vlnv xilinx.com:user:audio_codec_ctrl:1.0 audio_codec_ctrl_0
create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 clk_wiz_10MHz
set_property -dict [list CONFIG.PRIM_IN_FREQ {100.000} CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {10.000} CONFIG.RESET_PORT {resetn} CONFIG.RESET_TYPE {ACTIVE_LOW}] [get_bd_cells clk_wiz_10MHz]
create_bd_intf_port -mode Master -vlnv xilinx.com:interface:iic_rtl:1.0 IIC_1
connect_bd_intf_net [get_bd_intf_ports IIC_1] [get_bd_intf_pins ps7/IIC_1]
foreach {name direction} {bclk O lrclk O sdata_o O sdata_i I} {
    create_bd_port -dir $direction $name
    connect_bd_net [get_bd_ports $name] [get_bd_pins audio_codec_ctrl_0/$name]
}
create_bd_port -dir O -from 1 -to 0 codec_addr
connect_bd_net [get_bd_ports codec_addr] [get_bd_pins audio_codec_ctrl_0/codec_address]
create_bd_port -dir O -type clk audio_clk_10MHz
set_property CONFIG.FREQ_HZ {10000000} [get_bd_ports audio_clk_10MHz]
connect_bd_net [get_bd_ports audio_clk_10MHz] [get_bd_pins clk_wiz_10MHz/clk_out1]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 axi_dma_0
set_property -dict [list CONFIG.c_include_sg {0} CONFIG.c_sg_length_width {23} CONFIG.c_include_mm2s_dre {0} CONFIG.c_include_s2mm_dre {0} CONFIG.c_m_axi_mm2s_data_width {32} CONFIG.c_m_axi_s2mm_data_width {32} CONFIG.c_m_axis_mm2s_tdata_width {32} CONFIG.c_s_axis_s2mm_tdata_width {32}] [get_bd_cells axi_dma_0]
create_bd_cell -type module -reference audio_fir_axis audio_fir_0
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 filter_control
set_property -dict [list CONFIG.C_GPIO_WIDTH {2} CONFIG.C_ALL_OUTPUTS {1} CONFIG.C_DOUT_DEFAULT {0x00000001}] [get_bd_cells filter_control]
foreach {name bit} {bypass_slice 0 reset_slice 1} {
    create_bd_cell -type ip -vlnv xilinx.com:ip:xlslice:1.0 $name
    set_property -dict [list CONFIG.DIN_WIDTH {2} CONFIG.DIN_FROM $bit CONFIG.DIN_TO $bit CONFIG.DOUT_WIDTH {1}] [get_bd_cells $name]
    connect_bd_net [get_bd_pins filter_control/gpio_io_o] [get_bd_pins $name/Din]
}
connect_bd_net [get_bd_pins bypass_slice/Dout] [get_bd_pins audio_fir_0/bypass]
connect_bd_net [get_bd_pins reset_slice/Dout] [get_bd_pins audio_fir_0/soft_reset]
# Dual GPIO is an AXI-Lite mailbox, not a PS-controlled buzzer pin.
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 alarm_mailbox
set_property -dict [list CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO_WIDTH {32} CONFIG.C_ALL_OUTPUTS {1} CONFIG.C_DOUT_DEFAULT {0x00000000} CONFIG.C_GPIO2_WIDTH {32} CONFIG.C_ALL_INPUTS_2 {1}] [get_bd_cells alarm_mailbox]
create_bd_cell -type module -reference alarm_score alarm_score_0
connect_bd_net [get_bd_pins alarm_mailbox/gpio_io_o] [get_bd_pins alarm_score_0/command]
connect_bd_net [get_bd_pins alarm_score_0/status] [get_bd_pins alarm_mailbox/gpio2_io_i]
create_bd_port -dir O buzzer_a0_n
connect_bd_net [get_bd_pins alarm_score_0/buzzer_n] [get_bd_ports buzzer_a0_n]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 control_bus
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {4}] [get_bd_cells control_bus]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 memory_bus
set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {1}] [get_bd_cells memory_bus]
foreach {a b} {
    ps7/M_AXI_GP0 control_bus/S00_AXI
    control_bus/M00_AXI axi_dma_0/S_AXI_LITE
    control_bus/M01_AXI filter_control/S_AXI
    control_bus/M02_AXI audio_codec_ctrl_0/S_AXI
    control_bus/M03_AXI alarm_mailbox/S_AXI
    axi_dma_0/M_AXI_MM2S memory_bus/S00_AXI
    axi_dma_0/M_AXI_S2MM memory_bus/S01_AXI
    memory_bus/M00_AXI ps7/S_AXI_HP0
    axi_dma_0/M_AXIS_MM2S audio_fir_0/S_AXIS
    audio_fir_0/M_AXIS axi_dma_0/S_AXIS_S2MM
} {connect_bd_intf_net [get_bd_intf_pins $a] [get_bd_intf_pins $b]}
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_100m
set_property -dict [list CONFIG.C_EXT_RESET_HIGH {0} CONFIG.C_AUX_RESET_HIGH {1}] [get_bd_cells rst_100m]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 constant_one
set_property CONFIG.CONST_VAL {1} [get_bd_cells constant_one]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 constant_zero
set_property CONFIG.CONST_VAL {0} [get_bd_cells constant_zero]
connect_bd_net [get_bd_pins constant_one/dout] [get_bd_pins rst_100m/dcm_locked]
connect_bd_net [get_bd_pins constant_zero/dout] [get_bd_pins rst_100m/aux_reset_in] [get_bd_pins rst_100m/mb_debug_sys_rst]
connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N] [get_bd_pins rst_100m/ext_reset_in]
foreach pin {
    ps7/M_AXI_GP0_ACLK ps7/S_AXI_HP0_ACLK audio_fir_0/aclk
    axi_dma_0/s_axi_lite_aclk axi_dma_0/m_axi_mm2s_aclk axi_dma_0/m_axi_s2mm_aclk
    filter_control/s_axi_aclk rst_100m/slowest_sync_clk
    alarm_mailbox/s_axi_aclk alarm_score_0/aclk control_bus/M03_ACLK
    control_bus/ACLK control_bus/S00_ACLK control_bus/M00_ACLK control_bus/M01_ACLK control_bus/M02_ACLK
    audio_codec_ctrl_0/s_axi_aclk clk_wiz_10MHz/clk_in1
    memory_bus/ACLK memory_bus/S00_ACLK memory_bus/S01_ACLK memory_bus/M00_ACLK
} {connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins $pin]}
foreach pin {alarm_mailbox/s_axi_aresetn alarm_score_0/aresetn audio_fir_0/aresetn axi_dma_0/axi_resetn filter_control/s_axi_aresetn audio_codec_ctrl_0/s_axi_aresetn clk_wiz_10MHz/resetn} {
    connect_bd_net [get_bd_pins rst_100m/peripheral_aresetn] [get_bd_pins $pin]
}
foreach pin {
    control_bus/ARESETN control_bus/S00_ARESETN control_bus/M00_ARESETN control_bus/M01_ARESETN control_bus/M02_ARESETN control_bus/M03_ARESETN
    memory_bus/ARESETN memory_bus/S00_ARESETN memory_bus/S01_ARESETN memory_bus/M00_ARESETN
} {connect_bd_net [get_bd_pins rst_100m/interconnect_aresetn] [get_bd_pins $pin]}
# Preserve audio UIO mapping used by the existing PYNQ image (no IRQ required:
# libaudio uses mapped registers and polls the codec status).
assign_bd_address -offset 0x43C00000 -range 64K -target_address_space [get_bd_addr_spaces ps7/Data] [get_bd_addr_segs audio_codec_ctrl_0/S_AXI/reg0]
assign_bd_address -offset 0x41220000 -range 64K -target_address_space [get_bd_addr_spaces ps7/Data] [get_bd_addr_segs alarm_mailbox/S_AXI/Reg]
assign_bd_address
add_files -fileset constrs_1 [file join $root src constraints audio_pynqz2.xdc]
validate_bd_design
save_bd_design
set bd [get_files system.bd]
generate_target all $bd
set wrappers [make_wrapper -files $bd -top]
add_files -norecurse $wrappers
set_property top system_wrapper [get_filesets sources_1]
update_compile_order -fileset sources_1
puts "Project created. Review the block design, run build/scripts/run_sim.tcl in a separate Vivado session, then build/scripts/build_bitstream.tcl."
