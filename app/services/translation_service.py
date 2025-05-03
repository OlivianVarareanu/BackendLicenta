from transformers import AutoModelForSeq2SeqLM, NllbTokenizer
import torch

model_name = "facebook/nllb-200-1.3B"
tokenizer = NllbTokenizer.from_pretrained(model_name, use_fast=False)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)

# Dicționar de coduri de limbă ISO pentru NLLB
lang_code_map = {
    "ro": "ron_Latn",  # Română
    "en": "eng_Latn",  # Engleză
    "fr": "fra_Latn",  # Franceză
    "de": "deu_Latn",  # Germană
    "es": "spa_Latn",  # Spaniolă
}

def translate_text(text, target_lang):
    if target_lang not in lang_code_map:
        raise ValueError(f"Limba țintă '{target_lang}' nu este suportată.")

    tgt_lang = lang_code_map[target_lang]

    tokenizer.src_lang = "eng_Latn" 
    encoded = tokenizer(text, return_tensors="pt")
    tgt_lang_id = tokenizer.convert_tokens_to_ids(tgt_lang)
    generated_tokens = model.generate(**encoded, forced_bos_token_id=tgt_lang_id)

    translated = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]

    print(translated)
    return translated
