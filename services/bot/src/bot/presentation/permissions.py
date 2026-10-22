import discord

_DANGEROUS = (
    "administrator",
    "ban_members",
    "kick_members",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "manage_webhooks",
    "manage_messages",
    "mention_everyone",
    "moderate_members",
    "manage_nicknames",
)


def risky_permissions(permissions: discord.Permissions) -> list[str]:
    """Lista los permisos peligrosos que el bot no necesita y que tiene concedidos."""
    return [name for name in _DANGEROUS if getattr(permissions, name)]
