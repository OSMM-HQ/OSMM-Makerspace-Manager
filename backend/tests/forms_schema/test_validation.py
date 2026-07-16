import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.forms_schema.serializers import (
    CustomFormSchemaField,
    CustomFormSubmissionMixin,
)
from apps.forms_schema.validation import validate_answers, validate_form_schema


def question(question_id='contact', question_type='short_text', **overrides):
    value = {
        'id': question_id,
        'label': ' Contact name ',
        'type': question_type,
        'options': [],
        'required': True,
    }
    value.update(overrides)
    return value


def test_schema_canonicalizes_labels_options_and_empty_form():
    schema = [
        question(
            'slot',
            'dropdown',
            label=' Preferred slot ',
            options=[' Morning ', 'Evening'],
        )
    ]

    assert validate_form_schema([]) is None
    assert validate_form_schema(schema) == [
        {
            'id': 'slot',
            'label': 'Preferred slot',
            'type': 'dropdown',
            'options': ['Morning', 'Evening'],
            'required': True,
        }
    ]


@pytest.mark.parametrize(
    'schema',
    [
        {},
        [question(extra='no')],
        [question('bad id')],
        [question(), question()],
        [question(label='   ')],
        [question(question_type='email')],
        [question(required=1)],
        [question(options=['unexpected'])],
        [question(question_type='single_choice', options=[])],
        [question(question_type='single_choice', options=['same', ' same '])],
        [question(str(index)) for index in range(51)],
    ],
)
def test_schema_rejects_malformed_definitions(schema):
    with pytest.raises(DjangoValidationError):
        validate_form_schema(schema)


def test_schema_serializer_field_returns_canonical_value():
    field = CustomFormSchemaField()

    assert field.run_validation([question()])[0]['label'] == 'Contact name'
    with pytest.raises(serializers.ValidationError):
        field.run_validation([question(required=0)])


def test_submission_mixin_replaces_raw_answers_with_snapshot():
    class SubmissionSerializer(CustomFormSubmissionMixin, serializers.Serializer):
        name = serializers.CharField()

        def custom_form_schema(self):
            return self.context['schema']

    serializer = SubmissionSerializer(
        data={'name': 'Ada', 'custom_answers': {'contact': ' Grace '}},
        context={'schema': [question()]},
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data['custom_answers']['answers'][0]['value'] == 'Grace'
    assert 'custom_answers' not in serializer.data


def test_answers_snapshot_labels_types_and_schema_order():
    schema = [
        question('notes', 'paragraph', label=' Notes ', required=False),
        question(
            'tools',
            'multi_choice',
            label='Tools',
            options=['Lathe', 'Mill', 'Saw'],
        ),
        question('consent', 'yes_no', label='Consent'),
    ]

    result = validate_answers(
        schema,
        {
            'consent': 'TRUE',
            'notes': '  hello  ',
            'tools': ['Saw', 'Lathe'],
        },
    )

    assert result == {
        'version': 1,
        'answers': [
            {
                'id': 'notes',
                'label': 'Notes',
                'type': 'paragraph',
                'value': 'hello',
            },
            {
                'id': 'tools',
                'label': 'Tools',
                'type': 'multi_choice',
                'value': ['Lathe', 'Saw'],
            },
            {
                'id': 'consent',
                'label': 'Consent',
                'type': 'yes_no',
                'value': True,
            },
        ],
    }


@pytest.mark.parametrize(
    ('question_type', 'raw', 'expected'),
    [
        ('short_text', ' answer ', 'answer'),
        ('paragraph', ' details ', 'details'),
        ('number', '42', 42),
        ('number', '3.5', 3.5),
        ('date', '2026-07-17', '2026-07-17'),
        ('single_choice', 'A', 'A'),
        ('dropdown', 'B', 'B'),
        ('multi_choice', ['B', 'A'], ['A', 'B']),
        ('yes_no', 'no', False),
    ],
)
def test_each_answer_type_canonicalizes(question_type, raw, expected):
    has_options = 'choice' in question_type or question_type == 'dropdown'
    options = ['A', 'B'] if has_options else []
    schema = [question('value', question_type, options=options)]

    snapshot = validate_answers(schema, {'value': raw})

    assert snapshot['answers'][0]['value'] == expected


def test_optional_blank_is_omitted_and_no_answers_returns_null():
    schema = [question(required=False)]

    assert validate_answers(schema, {}) is None
    assert validate_answers(schema, {'contact': '  '}) is None
    assert validate_answers(None, {}) is None


@pytest.mark.parametrize('raw', [None, '', '   '])
def test_required_blank_answer_is_rejected_at_question(raw):
    with pytest.raises(serializers.ValidationError) as raised:
        validate_answers([question()], {'contact': raw})

    assert 'contact' in raised.value.detail['custom_answers']


def test_unknown_invalid_and_non_object_answers_are_rejected():
    with pytest.raises(serializers.ValidationError) as unknown:
        validate_answers(
            [question()],
            {'contact': 'ok', 'extra': 'secret'},
        )
    assert 'extra' in unknown.value.detail['custom_answers']

    with pytest.raises(serializers.ValidationError):
        validate_answers([question('day', 'date')], {'day': '2026-02-30'})
    with pytest.raises(serializers.ValidationError):
        validate_answers([question('count', 'number')], {'count': True})
    with pytest.raises(serializers.ValidationError):
        validate_answers(None, ['not', 'an', 'object'])
