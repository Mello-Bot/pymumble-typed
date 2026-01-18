from __future__ import annotations

# TODO(nico9889): implement a way to decode the Opus Stream "lazily"
#   The library user may leave the "sound_receive" variable on, but this doesn't mean that they need all the packets
#   decoded, resulting in a huge CPU waste.
#   So we need to help the user to decode by itself the packets, only when they are effectively needed!
#   The hard part is that an Audio Packet may depend on the following or on the previous one.
