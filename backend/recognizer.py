"""Local model adapter. No inference requests leave this process."""
from dataclasses import dataclass, field
import os
import re
import threading


def create_recognizer(local_only=None):
    """Use the same default on development machines and Linux servers."""
    engine = os.getenv('OCR_ENGINE', 'auto')
    if engine not in {'auto', 'rapidocr', 'trocr'}:
        raise ValueError('OCR_ENGINE must be auto, rapidocr, or trocr')
    if engine in {'auto', 'rapidocr'}:
        from .rapid_recognizer import RapidOCRRecognizer
        return RapidOCRRecognizer(local_only=local_only)
    return TrOCRRecognizer(local_only=local_only)

@dataclass
class Reading:
    text: str
    confidence: float
    raw_text: str = ''
    alternatives: list = field(default_factory=list)
    conflict: bool = False
    has_clock: bool = False


def time_token_trie(tokenizer):
    """Constrain complete clock strings, rather than unlimited digit tokens."""
    trie = {}
    for hour in range(24):
        for minute in range(60):
            for separator in (':', '.'):
                for suffix in ('', ' am', ' pm') if 1 <= hour <= 12 else ('',):
                    ids = tokenizer.encode(f'{hour}{separator}{minute:02d}{suffix}', add_special_tokens=False)
                    node = trie
                    for token in ids + [tokenizer.eos_token_id]:
                        node = node.setdefault(token, {})
    return trie

class UnavailableRecognizer:
    """Explicit manual mode; never a fake OCR success."""
    def read(self,image,mode='text'):
        return Reading('',0.0)

class TrOCRRecognizer:
    def __init__(self,model_path=None,local_only=None):
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        import torch
        torch.set_num_threads(int(os.getenv("OCR_CPU_THREADS","2")))
        self.torch=torch
        self.lock=threading.Lock()
        path=model_path or os.getenv('TROCR_MODEL','microsoft/trocr-base-handwritten')
        local_only = os.getenv('MODEL_LOCAL_ONLY','1')!='0' if local_only is None else local_only
        self.processor=TrOCRProcessor.from_pretrained(path,local_files_only=local_only)
        self.model=VisionEncoderDecoderModel.from_pretrained(path,local_files_only=local_only).eval()
        self.allowed=[]
        tokenizer=self.processor.tokenizer
        for token_id in range(len(tokenizer)):
            text=tokenizer.decode([token_id],skip_special_tokens=False)
            if re.fullmatch(r'[0-9:. ]+',text): self.allowed.append(token_id)
        self.allowed.append(tokenizer.eos_token_id)
        self.time_trie = time_token_trie(tokenizer)

    def time_tokens(self, batch, ids):
        node = self.time_trie
        for token in ids.tolist()[1:]:
            node = node.get(token, {})
        return list(node) or [self.processor.tokenizer.eos_token_id]

    def read(self,image,mode='text'):
        pixels=self.processor(images=image.convert('RGB'),return_tensors='pt').pixel_values
        options={'max_new_tokens':24 if mode in {'time','total'} else 48,'num_beams':1,'return_dict_in_generate':True,'output_scores':True}
        if mode in {'time','total'}:
            options['prefix_allowed_tokens_fn']=lambda batch,ids:self.allowed
        if mode == 'time':
            options['prefix_allowed_tokens_fn'] = self.time_tokens
            options['max_new_tokens'] = 16
        with self.lock,self.torch.inference_mode():
            output=self.model.generate(pixels,**options)
        text=self.processor.batch_decode(output.sequences,skip_special_tokens=True)[0].strip()
        probabilities=[float(self.torch.softmax(score,dim=-1)[0,int(output.sequences[0,i+1])]) for i,score in enumerate(output.scores)]
        confidence=min(probabilities,default=0)
        # Constrained likelihood isn't a calibrated correctness probability. Always require review.
        return Reading(text,min(confidence,.79))
