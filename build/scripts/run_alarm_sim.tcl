# Fresh Vivado session. Hardware timer parameters are accelerated only in testbench.
set root [file normalize [file join [file dirname [info script]] ../..]]
if {[llength [get_projects -quiet]]} {error "Use a fresh Vivado session for alarm simulation."}
create_project alarm_sim [file join $root alarm_sim_build] -part xc7z020clg400-1
add_files [file join $root src rtl alarm_score.v]
add_files -fileset sim_1 [file join $root sim tb_alarm_score.sv]
set_property top tb_alarm_score [get_filesets sim_1]
set_property xsim.simulate.runtime {0ns} [get_filesets sim_1]
launch_simulation
run all
