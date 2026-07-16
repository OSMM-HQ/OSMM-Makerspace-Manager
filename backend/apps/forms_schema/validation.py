import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers


ALLOWED_QUESTION_TYPES = (
    'short_text',
    'paragraph',
    'number',
    'date',
    'single_choice',
    'multi_choice',
    'dropdown',
    'yes_no',
)
CHOICE_QUESTION_TYPES = frozenset(
    {'single_choice', 'multi_choice', 'dropdown'}
)
QUESTION_KEYS = frozenset({'id', 'label', 'type', 'options', 'required'})
_QUESTION_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
_JSON_NUMBER_RE = re.compile(
    r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$'
)
_MISSING = object()


def _schema_error(index, field, message):
    raise DjangoValidationError(
        f'Question {index + 1} ({field}): {message}'
    )


def _canonical_question(question, index, seen_ids):
    if not isinstance(question, dict):
        _schema_error(index, 'question', 'Must be an object.')
    if set(question) != QUESTION_KEYS:
        missing = sorted(QUESTION_KEYS - set(question))
        unknown = sorted(set(question) - QUESTION_KEYS)
        detail = []
        if missing:
            detail.append('missing keys: ' + ', '.join(missing))
        if unknown:
            detail.append('unknown keys: ' + ', '.join(unknown))
        _schema_error(index, 'question', '; '.join(detail))

    question_id = question['id']
    if not isinstance(question_id, str) or not _QUESTION_ID_RE.fullmatch(
        question_id
    ):
        _schema_error(
            index,
            'id',
            'Use 1-64 letters, numbers, underscores, or hyphens.',
        )
    if question_id in seen_ids:
        _schema_error(index, 'id', 'Question IDs must be unique.')

    label = question['label']
    if not isinstance(label, str):
        _schema_error(index, 'label', 'Must be a string.')
    label = label.strip()
    if not label or len(label) > 200:
        _schema_error(index, 'label', 'Must contain 1-200 characters.')

    question_type = question['type']
    if question_type not in ALLOWED_QUESTION_TYPES:
        _schema_error(index, 'type', 'Unsupported question type.')
    if type(question['required']) is not bool:
        _schema_error(index, 'required', 'Must be a JSON boolean.')

    options = question['options']
    if not isinstance(options, list):
        _schema_error(index, 'options', 'Must be an array.')
    canonical_options = []
    if question_type in CHOICE_QUESTION_TYPES:
        if not 1 <= len(options) <= 50:
            _schema_error(index, 'options', 'Must contain 1-50 choices.')
        for option in options:
            if not isinstance(option, str):
                _schema_error(index, 'options', 'Every choice must be a string.')
            option = option.strip()
            if not option or len(option) > 200:
                _schema_error(
                    index,
                    'options',
                    'Every choice must contain 1-200 characters.',
                )
            if option in canonical_options:
                _schema_error(index, 'options', 'Choices must be unique.')
            canonical_options.append(option)
    elif options:
        _schema_error(index, 'options', 'Must be empty for this question type.')

    seen_ids.add(question_id)
    return {
        'id': question_id,
        'label': label,
        'type': question_type,
        'options': canonical_options,
        'required': question['required'],
    }


def validate_form_schema(value):
    '''Validate and return the canonical ordered custom-form schema.'''
    if value is None:
        return None
    if not isinstance(value, list):
        raise DjangoValidationError('A custom form must be an array or null.')
    if not value:
        return None
    if len(value) > 50:
        raise DjangoValidationError('A custom form may contain at most 50 questions.')

    seen_ids = set()
    return [
        _canonical_question(question, index, seen_ids)
        for index, question in enumerate(value)
    ]


def _canonical_number(value):
    if type(value) is bool:
        raise ValueError
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError
        return value
    if not isinstance(value, str):
        raise ValueError
    raw = value.strip()
    if not _JSON_NUMBER_RE.fullmatch(raw):
        raise ValueError
    try:
        parsed = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError from exc
    if not parsed.is_finite():
        raise ValueError
    if '.' not in raw and 'e' not in raw.lower():
        return int(parsed)
    converted = float(parsed)
    if not math.isfinite(converted):
        raise ValueError
    return converted


def _canonical_answer(question, value):
    question_type = question['type']
    if question_type in {'short_text', 'paragraph'}:
        if not isinstance(value, str):
            raise ValueError('Must be a string.')
        value = value.strip()
        limit = 500 if question_type == 'short_text' else 5_000
        if len(value) > limit:
            raise ValueError(f'Must be at most {limit} characters.')
        return value
    if question_type == 'number':
        try:
            return _canonical_number(value)
        except ValueError as exc:
            raise ValueError('Must be a finite number.') from exc
    if question_type == 'date':
        if not isinstance(value, str) or not re.fullmatch(
            r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value
        ):
            raise ValueError('Must be a date in YYYY-MM-DD format.')
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError('Must be a real calendar date.') from exc
        return value
    if question_type in {'single_choice', 'dropdown'}:
        if not isinstance(value, str) or value not in question['options']:
            raise ValueError('Must be one of the configured choices.')
        return value
    if question_type == 'multi_choice':
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise ValueError('Must be an array of configured choices.')
        if len(value) != len(set(value)):
            raise ValueError('Choices must not be repeated.')
        if any(item not in question['options'] for item in value):
            raise ValueError('Must contain only configured choices.')
        selected = set(value)
        return [option for option in question['options'] if option in selected]
    if question_type == 'yes_no':
        if type(value) is bool:
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {'yes', 'true'}:
                return True
            if normalized in {'no', 'false'}:
                return False
        raise ValueError('Must be yes or no.')
    raise ValueError('Unsupported question type.')


def _is_unanswered(value):
    return (
        value is _MISSING
        or value is None
        or (isinstance(value, str) and not value.strip())
        or value == []
    )


def validate_answers(schema, raw_answers):
    '''Validate raw answers and return the canonical private snapshot.'''
    try:
        canonical_schema = validate_form_schema(schema)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(
            {'custom_answers': exc.messages}
        ) from exc

    if raw_answers is None:
        raw_answers = {}
    if not isinstance(raw_answers, dict):
        raise serializers.ValidationError(
            {'custom_answers': 'Must be an object or null.'}
        )

    questions = canonical_schema or []
    known_ids = {question['id'] for question in questions}
    errors = {
        str(question_id): 'Unknown question ID.'
        for question_id in raw_answers
        if question_id not in known_ids
    }
    answers = []
    for question in questions:
        question_id = question['id']
        raw_value = raw_answers.get(question_id, _MISSING)
        if _is_unanswered(raw_value):
            if question['required']:
                errors[question_id] = 'This question is required.'
            continue
        try:
            value = _canonical_answer(question, raw_value)
        except ValueError as exc:
            errors[question_id] = str(exc)
            continue
        answers.append(
            {
                'id': question_id,
                'label': question['label'],
                'type': question['type'],
                'value': value,
            }
        )

    if errors:
        raise serializers.ValidationError({'custom_answers': errors})
    if not answers:
        return None
    return {'version': 1, 'answers': answers}
