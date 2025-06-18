import gettext, pathlib, os, configparser, sys
moonraker_path = pathlib.Path(__file__).parent.resolve()
lang_path = os.path.join(moonraker_path, "locales")
gettext.translation('moonraker', localedir=lang_path, languages=["ru"], fallback=True).install()

def set_locale():
    try:
        config_file = sys.argv[1]
        config = configparser.ConfigParser()
        config.read(config_file)
        lang_list = [d for d in os.listdir(lang_path) if not os.path.isfile(os.path.join(lang_path, d))]
        lang_list.sort()
        langs = {}
        for lng in lang_list:
            langs[lng] = gettext.translation('moonraker', localedir=lang_path, languages=[lng], fallback=True)
        lang = config.get("server", "lang", fallback='ru')
        if lang in lang_list:
            langs[lang].install()
    except:
        return