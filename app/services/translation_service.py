from googletrans import Translator

def translate_text(text, target_lang):
    translator = Translator()
    result = translator.translate(text, dest=target_lang)
    print(result.text)

    if result.text is None:
        raise ValueError(f"Nu s-a obținut niciun rezultat pentru traducerea textului: {text}")
    return result.text
