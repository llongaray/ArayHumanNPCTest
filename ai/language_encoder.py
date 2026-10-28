"""CPU encoder boundary. No model download, import of ML runtimes, or synthetic vectors."""
import math


class LanguageEncoder:
    schema_version = 1

    def __init__(self, backend=None, model_id=None):
        # Only a trusted local adapter can be injected explicitly; never from a request.
        self.backend, self.model_id = backend, model_id

    def encode(self, text):
        out = {"schema_version": 1, "status": "UNAVAILABLE", "model_id": self.model_id,
               "vector": None, "dimensions": None, "reason": "no_local_encoder_configured"}
        if not isinstance(text, str) or len(text.encode('utf-8')) > 2000:
            out['reason'] = 'message_budget'; return out
        if self.backend is None: return out
        try:
            vector = self.backend(text)
            if not isinstance(vector, (list, tuple)) or not 1 <= len(vector) <= 768:
                raise ValueError('embedding_dimensions')
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in vector):
                raise ValueError('embedding_values')
            out.update(status='AVAILABLE', vector=list(vector), dimensions=len(vector), reason=None)
        except Exception:
            out['reason'] = 'encoder_failed'
        return out
