def classFactory(iface):
    from .plugin import SIGMAIPlugin

    return SIGMAIPlugin(iface)
