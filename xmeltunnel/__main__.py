import sys

if "--route-helper" in sys.argv or "--route-helper-task" in sys.argv:  # elevated helper of the routing mode: no UI, no Qt
    from xmeltunnel.routing import helper_main

    sys.exit(helper_main(sys.argv))

from xmeltunnel.ui.app import main

sys.exit(main())
