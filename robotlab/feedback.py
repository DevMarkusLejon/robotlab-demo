"""Swedish operator feedback, independent of camera and robot libraries."""
STAGES = {
    'ready': 'Din tur. Peka på en tom ruta och håll kvar.',
    'planning': 'Drag accepterat. Planerar robotens rörelse…',
    'robot_turn': 'Robotens tur. Väljer motdrag…',
    'approach_supply': 'Roboten hämtar en pjäs…',
    'contact_supply': 'Roboten greppar pjäsen…',
    'lift': 'Greppet bekräftat. Lyfter pjäsen…',
    'transfer': 'Roboten flyttar pjäsen till brädet…',
    'lower_to_board': 'Roboten placerar pjäsen…',
    'retract': 'Pjäsen släppt. Drar tillbaka gripdonet…',
    'return_home': 'Roboten återgår till startpositionen…',
    'camera_confirmation': 'Kontrollerar placeringen med kameran…',
    'placement_verified': 'Placeringen är bekräftad.',
    'release': 'Ta bort handen från rutnätet innan nästa drag.',
    'busy': 'Roboten arbetar. Vänta innan du väljer nästa ruta.',
    'complete': 'Spelet är slut. Välj Nytt spel i startfönstret.',
}
ERRORS = {
    'no_fresh_board_camera_image': 'Brädkameran ger inga nya bilder.',
    'camera_placement_not_confirmed': 'Kameran kunde inte bekräfta rätt placering.',
    'grasp_contact_not_confirmed': 'Gripdonet fick inte ett bekräftat grepp.',
    'token_not_lifted': 'Pjäsen följde inte med gripdonet.',
    'release_not_confirmed': 'Pjäsen lossnade inte som väntat.',
    'token_placement_mismatch': 'Pjäsen hamnade inte på förväntad plats.',
    'baseline_board_mismatch': 'Kamerabilden stämmer inte med det senaste bekräftade brädet.',
    'stale_or_future_frame': 'Pekningen kom för sent. Peka på nytt.',
    'outside_or_illegal_target': 'Välj en tom ruta.',
    'low_confidence': 'Handen syns otydligt. Prova bättre ljus.',
    'gesture_not_confirmed': 'Visa ett utsträckt pekfinger.',
    'client_disconnected': 'Kontakten med kamerafönstret försvann innan rörelsen startade.',
    'action_timeout': 'Simulatorn svarade inte inom rörelsens tidsgräns.',
    'token_selection_not_confirmed': 'Nästa pjäs kunde inte förberedas.',
    'moveit_plan_rejected': 'Ingen godkänd rörelseplan hittades.',
    'pick_start_collision': 'Robotens startläge ger en kollision i simuleringen.',
}


def error_message(error):
    code = str(error).split(':', 1)[0]
    return ERRORS.get(code, 'Försöket kunde inte slutföras.') + ' Starta ett nytt spel för att återställa scenen.'


def feedback(status, result=None):
    if status.get('terminal') or status.get('busy'):
        return status.get('message', STAGES['busy'])
    result = result or status
    if result.get('stage') == 'confirming':
        return f"Ruta {result['cell'] + 1}: håll kvar ({result['stable_frames']}/12)."
    if status.get('rearm_required'):
        return STAGES['release']
    return ERRORS.get(result.get('reason'), STAGES.get(result.get('stage'), STAGES['ready']))
