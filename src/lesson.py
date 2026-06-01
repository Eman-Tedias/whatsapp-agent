from random import randint

_CAMPOS = [
    {"pergunta": "Poderia descrever como foi a aula?", "campo": "description", "tipo": "texto livre", "label": "Descrição"},
    {"pergunta": "Quantos alunos compareceram?", "campo": "student_count", "tipo": "número inteiro", "label": "Alunos presentes"},
]

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