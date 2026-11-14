class UserError(Exception):
    """Erreur destinée à l'utilisateur : le message doit être clair et sans jargon."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status
