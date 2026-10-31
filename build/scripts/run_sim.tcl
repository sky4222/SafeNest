# Fresh Vivado session, no synthesis. Full simulation has a 30 ms watchdog.
set root [file normalize [file join [file dirname [info script]] ../..]]
if {[llength [get_projects -quiet]]} {error "Use a fresh Vivado session for this simulation project."}
if {[file exists [file join $root sim_build fir_sim.xpr]]} {error "Open existing sim_build/fir_sim.xpr instead, then launch simulation and run all."}
create_project fir_sim [file join $root sim_build] -part xc7z020clg400-1
add_files [list [file join $root src rtl audio_fir_axis.v] [file join $root src rtl fir_coeffs.vh]]
set_property include_dirs [list [file join $root src rtl]] [get_filesets sources_1]
add_files -fileset sim_1 [list [file join $root sim tb_audio_fir.sv] [file join $root sim input.mem] [file join $root sim expected.mem]]
set_property top tb_audio_fir [get_filesets sim_1]
set_property xsim.simulate.runtime {0ns} [get_filesets sim_1]
launch_simulation
run all
# Only the testbench PASS message confirms correctness. $fatal means failure.
