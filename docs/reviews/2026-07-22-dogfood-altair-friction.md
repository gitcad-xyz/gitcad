# Dogfood friction log � mech pass

- hole op needed explicit inputs=[body]; first attempt silently created disconnected features � want an implicit 'apply to last body' mode or an error when a subtractive op has no input
- cylinder axes are always +Z; laying a cell horizontally required rotate about X with non-obvious sign/translation � want axis-aligned primitive placement (cylinder(axis='y'))
- cylinder axes are always +Z; laying a cell horizontally required rotate about X with non-obvious sign/translation � want axis-aligned primitive placement (cylinder(axis='y'))

# Dogfood friction log — ecad pass

- hand-routing in text requires computing every pad's absolute position mentally — want a pad_position query tool and a route(net, from_pad, to_pad, waypoints) helper
- a zero-length track passed the fab gate silently in an earlier iteration — board_validate should flag degenerate tracks
- connectivity caught bottom-copper-to-SMD-top-pad with no vias (3 GND islands) — the check chain repeatedly caught what manual planning missed; an interactive route helper would prevent, not just detect
- GND on through-hole J1.2 could route on bottom only because J1 is through-hole — SMD-only boards need vias planned by hand; want an auto-via-on-layer-change in a route helper

# Dogfood friction log — assembly pass

- no board->3D bridge: had to hand-extrude the board outline x thickness as a mech model for interference — want board_to_model(board) producing outline+thickness (+ component height keepouts) automatically
- housing has no physical bosses (no boss/standoff feature op) — ports are declared at the right coordinates but the geometry underneath is bare floor; want a boss feature (cylinder+fillet+pilot hole) and port-from-feature derivation for mech
