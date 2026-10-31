"""Display/log decision rule for existing model scores, not event durations.
Class order: dialogue=0, impact=1, scream=2, footsteps=3.
"""
import math


def priority_event_decision(scores, model_class_id, threshold=0.25):
    threshold=float(threshold)
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('threshold must be finite and in [0,1]')
    values=[float(v) for v in scores]
    if len(values)!=4 or not all(math.isfinite(v) and 0<=v<=1 for v in values):
        raise ValueError('Expected four finite model scores in [0,1]')
    if model_class_id not in (0,1,2,3):
        raise ValueError('Unexpected model class id')
    eligible=[i for i in (1,2) if values[i] > threshold]
    if eligible:
        # A tie deterministically selects impact (id 1); no rounding before compare.
        chosen=max(eligible,key=lambda i:values[i])
        return {'class_id':chosen,'priority_applied':True,
                'reason':'impact_or_scream_score_strictly_above_threshold',
                'threshold':threshold}
    return {'class_id':int(model_class_id),'priority_applied':False,
            'reason':'neither_priority_score_strictly_above_threshold',
            'threshold':threshold}
