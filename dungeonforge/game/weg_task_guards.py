"""Other actions cannot spend an actor already reserved for exclusive work."""
from dungeonforge.rules.weg_tasks import busy_actor_ids


def require_available(session, *actor_ids):
    if busy_actor_ids(session).intersection(actor_ids):
        raise ValueError("This character is reserved for a saved exclusive task. Finish or cancel that project before another action.")
    from dungeonforge.rules.weg_medical import busy_actor_ids as medical_busy
    if medical_busy(session).intersection(actor_ids):
        raise ValueError("This character is reserved for saved bacta treatment or prescribed rest. Finish or cancel that medical project before another action.")
