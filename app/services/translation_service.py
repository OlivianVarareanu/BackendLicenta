from transformers import AutoModelForSeq2SeqLM, NllbTokenizer
import torch

model_name = "facebook/nllb-200-1.3B"
tokenizer = NllbTokenizer.from_pretrained(model_name, use_fast=False)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = model.to(device)

lang_code_map = {
    "ro": "ron_Latn",
    "en": "eng_Latn",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "es": "spa_Latn",
    "it": "ita_Latn", 
    "ru": "rus_Cyrl",
}

def translate_text(text, target_lang, original_lang):
    if target_lang not in lang_code_map:
        raise ValueError(f"Limba '{target_lang}' nu este suportată.")
    if original_lang not in lang_code_map:
        raise ValueError(f"Limba sursă '{original_lang}' nu este suportată.")

    tgt_lang = lang_code_map[target_lang]
    tokenizer.src_lang = lang_code_map[original_lang]

    encoded = tokenizer(text, return_tensors="pt").to(device)
    tgt_lang_id = tokenizer.convert_tokens_to_ids(tgt_lang)

    generated_tokens = model.generate(
        **encoded,
        forced_bos_token_id=tgt_lang_id,
        num_beams=5,
        max_length=512
    )

    translated = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]
    return translated
