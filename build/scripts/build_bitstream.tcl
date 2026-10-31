# Source after create_project.tcl. This step may take several minutes.
set root [file normalize [file join [file dirname [info script]] ../..]]
if {[get_property NAME [current_project]] ne "safenest_audio"} {error "Open the safenest_audio project first."}
launch_runs synth_1 -jobs 2
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis failed. Read the run log."}
launch_runs impl_1 -to_step write_bitstream -jobs 2
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Implementation failed. Read the run log."}
open_run impl_1
file mkdir [file join $root reports]
report_utilization -file [file join $root reports utilization.rpt]
report_timing_summary -file [file join $root reports timing.rpt]
report_drc -file [file join $root reports drc.rpt]
set paths [get_timing_paths -delay_type max -max_paths 1]
if {![llength $paths] || [get_property SLACK [lindex $paths 0]] < 0} {error "Setup timing not met; inspect reports before using bitstream."}
set holds [get_timing_paths -delay_type min -max_paths 1]
if {![llength $holds] || [get_property SLACK [lindex $holds 0]] < 0} {error "Hold timing not met; inspect reports before using bitstream."}
set hwh [file join $root build safenest_audio.gen sources_1 bd system hw_handoff system.hwh]
set bit [file join $root build safenest_audio.runs impl_1 system_wrapper.bit]
if {![file exists $hwh] || ![file exists $bit]} {error "Expected .bit/.hwh missing. Inspect generated outputs."}
file copy -force $bit [file join $root board safenest_audio.bit]
file copy -force $hwh [file join $root board safenest_audio.hwh]
puts "Exported board/safenest_audio.bit and board/safenest_audio.hwh. Review reports and then test DMA bypass on the board."

open_bd_design [get_files system.bd]
write_bd_tcl -force [file join $root board safenest_audio.tcl]
