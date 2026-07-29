from random import randint

_CAMPOS = [
    {"pergunta": "Poderia descrever como foi a aula?", "campo": "description", "tipo": "texto livre", "label": "Descrição"},
    {"pergunta": "Quantos alunos compareceram?", "campo": "student_count", "tipo": "número inteiro", "label": "Alunos presentes"},
    {"pergunta": "Agora envie as fotos dos alunos (pode mandar mais de uma). Quando terminar, me avise.", "campo": "fotos_alunos", "tipo": "imagem", "label": "Fotos dos alunos"},
    {"pergunta": "Agora envie a foto da folha de chamada (pode mandar mais de uma). Quando terminar, me avise.", "campo": "folha_chamada", "tipo": "imagem", "label": "Folha de chamada"},
]

_CAMPOS_TEXTO = [c for c in _CAMPOS if c["tipo"] != "imagem"]
_CAMPOS_IMAGEM = [c for c in _CAMPOS if c["tipo"] == "imagem"]

coleta_model = {c["campo"]: None for c in _CAMPOS}

json_model_template = {
    "lesson_id": randint(1111, 4444),
    "educator_id": 1234,
    "educator_name": "Eman",
    "lesson_date": "2026-05-28",
    "lesson_time": "09:00",
    "class_name": "Turma B - Alfabetização",
    "location": "Sala 3",
    "description": None,
    "student_count": None,
    "status": "draft"
}