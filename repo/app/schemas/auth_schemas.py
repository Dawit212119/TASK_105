from marshmallow import Schema, fields, validate, EXCLUDE


class RegisterSchema(Schema):
    class Meta:
        unknown = EXCLUDE  # silently ignore any extra fields (e.g. role) sent by clients

    username = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=64, error="Username must be between 1 and 64 characters"),
    )
    # Password min-length business rule enforced in AuthService (returns password_too_short error code)
    password = fields.Str(required=True, load_only=True)


class LoginSchema(Schema):
    username = fields.Str(required=True)
    password = fields.Str(required=True, load_only=True)
