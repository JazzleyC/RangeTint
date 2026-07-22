import nuke


if nuke.GUI:
    import range_tint

    # Startup stays passive: no timers or Viewer overlays are created.
    range_tint.register_menu()
