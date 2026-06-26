"""Self-developed online-learning loop (the moat): each deployment gets more accurate on ITS data from
user feedback, without retraining any foundation model.

feedback_log — log impressions + implicit/explicit feedback (the training asset).
(fusion_ranker / embed_adapter — IPS-debiased learning-to-rank; activate once feedback accrues.)
"""
