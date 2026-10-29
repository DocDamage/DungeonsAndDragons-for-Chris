"""Reviewed Reloaded story milestones award the stated XP to each eligible PC."""
from dungeonforge.campaign.strahd import ARCHIVE, ARCS, arc_sources
from dungeonforge.rules.strahd_models import (
    StrahdArcReview, StrahdMilestone, StrahdMilestoneAward, StrahdXPAccount, StrahdXPAllocation,
)


XP_THRESHOLDS = (0, 300, 900, 2700, 6500, 14000, 23000, 34000, 48000, 64000,
    85000, 100000, 120000, 140000, 165000, 195000, 225000, 265000, 305000, 355000)
XP_SOURCE = "5e/Player's Handbook.pdf, PDF p.12, Character Advancement table."
_PATHS = {item["id"]: item["path"] for item in arc_sources()}


def milestone(id, title, arcs, xp, trigger, *, prerequisites=(), variants=None, notes=()):
    return StrahdMilestone(id=id, title=title, arcs=list(arcs), xp_per_pc=xp,
        trigger=trigger, source_path=f"{ARCHIVE}!/{_PATHS[arcs[0]]}",
        prerequisite_ids=list(prerequisites), variants=variants or {}, notes=list(notes))


CATALOG = [
    milestone("a_secret_stairs", "Descend the secret stairs", "A", 200, "The party exits the secret stairs into Death House's dungeon."),
    milestone("a_escape_rest", "Escape Death House and begin a long rest", "A", 400, "The party begins its first long rest after escaping Death House."),
    milestone("b_depart_with_ireena", "Defend Barovia and depart with Ireena", "B", 400, "After defending the village and burying the Burgomaster, the party departs Barovia with Ireena."),
    milestone("b_doru_test", "Doru passes his test of will", "B", 100, "At the departure milestone, Doru has successfully passed his test of will.", prerequisites=("b_depart_with_ireena",)),
    milestone("c_tarokka", "Receive the Tarokka reading and depart", "C", 500, "After the Tarokka reading, the party departs the crossroads."),
    milestone("c_vallaki_rest", "Begin the first long rest in Vallaki", "C", 1000, "The party takes its first long rest in Vallaki; arrival alone is not the detailed scene trigger."),
    milestone("c_ireena_escort", "Escort Ireena to Vallaki", "C", 250, "At the first Vallaki long rest, the party has successfully escorted Ireena to Vallaki; reaching St. Andral's is not required.", prerequisites=("c_vallaki_rest",)),
    milestone("d_bones", "Restore St. Andral's bones", "D", 1250, "The bones of St. Andral are returned to the church."),
    milestone("e_arabelle", "Find Arabelle and hear her prophecy", "E", 1250, "After Arabelle is found, she delivers her prophecy."),
    milestone("fg_izek", "Resolve the Izek rescue or defeat milestone", "FG", None,
        "Arc F: Lady Wachter takes power after Izek is assassinated. Arc G: Ireena is escorted to safety; use the larger award if Izek was defeated.",
        variants={"rescue_without_defeat": 750, "izek_defeated": 1500},
        notes=("F/G share one canonical milestone. Select the actual final outcome; the 750 and 1,500 awards are alternatives, not cumulative claims.",)),
    milestone("h_stella", "Restore Stella's soul", "H", 1750, "Stella is rescued from the Ethereal Plane and her soul restored to her body."),
    milestone("h_tome", "Obtain the Tome of Strahd", "H", 750, "The party actually obtains the Tome of Strahd.", notes=("The Adventure Summary's XP cell is blank; Arc H and Act II Summary explicitly supply 750 XP.",)),
    milestone("i_krezk", "Gain safe passage through Krezk's gates", "I", 750, "After obtaining Baba Lysaga's aid, the party first gains safe passage through Krezk's village gates."),
    milestone("j_winery", "Reclaim the winery", "J", 2000, "The party defeats Lorghoth and breaks his Gulthias staff."),
    milestone("j_gem", "Return the stolen gem", "J", 2500, "Following Yester Hill, the party returns the stolen gem to Davian Martikov."),
    milestone("k_ezmerelda", "Recruit Ezmerelda and complete the seance", "K", 1000, "The party completes the seance in the Ezmerelda recruitment sequence."),
    milestone("l_bargain_escape", "Escape after making Zuleika's bargain", "L", 1500, "The party successfully escapes the werewolf den after making a deal with Zuleika."),
    milestone("l_free_captives", "Free Ilya and Zuleika", "L", 250, "In addition to the bargain-and-escape milestone, the party also frees Ilya and Zuleika from the den.", prerequisites=("l_bargain_escape",)),
    milestone("m_prophecy", "Receive Argynvost's quest", "M", 2500, "The party obtains the dragon gargoyle's prophecy at Argynvostholt."),
    milestone("o_dinner", "Depart Ravenloft after dinner and Varushka", "O", 3500, "After dining with Strahd and vanquishing Varushka, the party departs Ravenloft."),
    milestone("o_necklace_cache", "Return Katarina's necklace and retrieve the cache", "O", 500, "At the dinner departure milestone, the party has reunited Varushka with Katarina's necklace and retrieved her hidden cache.", prerequisites=("o_dinner",)),
    milestone("p_skull", "Depart Ravenloft with Argynvost's skull", "P", 4000, "The party departs Ravenloft after stealing Argynvost's skull."),
    milestone("p_icon", "Depart with the Icon of Dawn's Grace", "P", 250, "The party departs Ravenloft after obtaining the Icon of Dawn's Grace from St. Markovia's crypt."),
    milestone("p_emil", "Depart after rescuing Emil", "P", 250, "The party departs Ravenloft after rescuing Emil Toranescu."),
    milestone("p_gertruda", "Depart after rescuing Gertruda", "P", 250, "The party departs Ravenloft after rescuing Gertruda."),
    milestone("p_spear", "Depart with the Spear of the Huntress", "P", 250, "The party departs Ravenloft after obtaining the Spear of the Huntress from King Dostron's crypt."),
    milestone("p_treasury", "Depart after looting Strahd's treasury", "P", 250, "The party departs Ravenloft after looting Strahd's treasury."),
    milestone("q_abbot", "Free the Abbey and Krezk from the Abbot", "Q", 2000, "The party defeats the Abbot and frees the Abbey and Krezk from his control."),
    milestone("q_redeem_abbot", "Redeem the defeated Abbot", "Q", 500, "The party also redeems the defeated Abbot, making the complete award 2,500 XP.", prerequisites=("q_abbot",)),
    milestone("q_kiril", "Defeat Kiril", "Q", 2000, "The party defeats Kiril Stoyanovich."),
    milestone("q_beacon", "Light Argynvost's beacon", "Q", 3000, "After returning Argynvost's skull to his crypt, the party lights the beacon."),
    milestone("r_burebis", "Receive Burebis's mission", "R", 5000, "The party departs the Shrine of the Rozana after receiving Burebis's mission."),
    milestone("r_amber_temple", "Reach the Amber Temple", "R", 5000, "The party arrives outside the Amber Temple."),
    milestone("s_sunsword", "Obtain the cleansed Sunsword hilt", "S", 8000, "After defeating Patrina, the party obtains the cleansed Sunsword hilt."),
    milestone("t_swamp", "Claim the Weaver's boon", "T", 5500, "After reconsecrating the Swamp Fane, the party claims the boon of the Weaver."),
    milestone("t_forest", "Claim the Huntress's boon", "T", 5500, "After reconsecrating the Forest Fane, the party claims the boon of the Huntress."),
    milestone("t_mountain", "Claim the Seeker's boon", "T", 5500, "After reconsecrating the Mountain Fane, the party claims the boon of the Seeker."),
    milestone("u_sunrise", "Defeat Strahd and witness sunrise", "U", 25000, "After Strahd is defeated, the sun rises."),
]
BY_ID = {item.id: item for item in CATALOG}
BY_ID["fg_izek"].source_path += f"; {ARCHIVE}!/{_PATHS['G']}"
NOTES = [
    "Reloaded awards the listed XP to each eligible player character; it is not a party pool to divide. NPC allies are not automatically player characters.",
    "Only explicitly listed story milestones grant XP. Monster statblock XP, narration, quest selection and arc status do not grant rewards.",
    "The GM confirms actual completion and reviews every enrolled PC currently in the party. Exclusions require a reason; absent or newly added characters cannot reclaim an old event.",
    "Source scene triggers take precedence over shorthand summary tables. Conditional bonus milestones require the corresponding recorded base award.",
    "Ledger XP and suggested levels do not update the character sheet. Review class choices, HP, proficiency, spells and other features before editing a sheet to the earned level.",
    "Older saves begin with unknown XP and unreviewed arcs. Enroll actual PCs with their GM-confirmed absolute baseline XP; no past milestones are reconstructed.",
]


def people(session):
    return {person.id: person for person in [session.character, *session.character.companions]}


def xp_level(xp):
    return max(index + 1 for index, value in enumerate(XP_THRESHOLDS) if xp >= value)


def register(session, req):
    members = people(session)
    accounts = {item.actor_id for item in session.strahd_progress.accounts}
    ids = [item.actor_id for item in req.actors]
    if len(ids) != len(set(ids)) or set(ids) & accounts:
        raise ValueError("Enroll each actual PC once. Existing XP accounts and prior milestone claims cannot be reset by registration.")
    records = []
    for item in req.actors:
        person = members.get(item.actor_id)
        if person is None or person.d6 is not None or not item.pc_confirmed or not item.reason.strip():
            raise ValueError("Select an actual 5e party actor, confirm they are a player character, and explain their reviewed baseline XP.")
        if not 1 <= person.level <= 20 or item.baseline_xp < XP_THRESHOLDS[person.level - 1]:
            raise ValueError("The absolute baseline XP must support the actor's current 2014 sheet level; review legacy XP explicitly.")
        records.append(StrahdXPAccount(actor_id=person.id, name=person.name, baseline_xp=item.baseline_xp, baseline_reason=item.reason.strip()))
    session.strahd_progress.accounts.extend(records)
    return records


def award(session, req):
    state = session.strahd_progress
    item = BY_ID.get(req.milestone_id)
    if item is None:
        raise ValueError("Select an actual source-listed Reloaded story milestone; ordinary monster kills grant no XP.")
    if not req.completion_confirmed or not req.reason.strip():
        raise ValueError("The GM must confirm the actual source trigger and record how the milestone was completed.")
    if item.id == "a_escape_rest" and state.death_house.status not in {"unstarted", "escaped"}:
        raise ValueError("The saved Death House clock still records the party inside. Review the actual escape before claiming its first post-escape long-rest milestone; no exit is inferred from an XP request.")
    if any(previous.milestone_id == item.id for previous in state.awards):
        raise ValueError("This source milestone or its alternative outcome has already been awarded; it cannot be claimed again.")
    if item.variants:
        if req.variant not in item.variants:
            raise ValueError("Select the actual source outcome variant before allocating this milestone's XP.")
        xp = item.variants[req.variant]
    else:
        if req.variant is not None:
            raise ValueError("This source milestone has no alternate XP outcome.")
        xp = item.xp_per_pc
    prior = {record.milestone_id: record for record in state.awards}
    if set(item.prerequisite_ids) - set(prior):
        raise ValueError("Record the source milestone's base award before its conditional bonus.")
    members = people(session)
    accounts = {record.actor_id: record for record in state.accounts if record.actor_id in members}
    ids = [review.actor_id for review in req.reviews]
    if not accounts or len(ids) != len(set(ids)) or set(ids) != set(accounts):
        raise ValueError("Review every enrolled PC currently present in the actual party exactly once.")
    allocations = []
    for review in req.reviews:
        if not review.reason.strip():
            raise ValueError("Record participation or the actual reason for excluding each reviewed PC.")
        if not review.eligible:
            continue
        for prerequisite in item.prerequisite_ids:
            if review.actor_id not in {entry.actor_id for entry in prior[prerequisite].allocations}:
                raise ValueError("A conditional bonus recipient must also have received its corresponding source base award.")
        account, person = accounts[review.actor_id], members[review.actor_id]
        total = account.baseline_xp + account.awarded_xp + xp
        if total > 1000000000:
            raise ValueError("The milestone would exceed the supported XP ledger limit.")
        target = xp_level(total)
        allocations.append(StrahdXPAllocation(actor_id=person.id, name=person.name, xp=xp, total_xp=total,
            sheet_level=person.level, xp_level=target, level_up_pending=target > person.level))
    if not allocations:
        raise ValueError("A reward review needs at least one actual eligible PC; use arc review to record progress without XP.")
    record = StrahdMilestoneAward(milestone_id=item.id, title=item.title, variant=req.variant, xp_per_pc=xp,
        reason=req.reason.strip(), source_path=item.source_path, trigger=item.trigger, reviews=req.reviews, allocations=allocations)
    for allocation in allocations:
        accounts[allocation.actor_id].awarded_xp += allocation.xp
    state.awards.append(record)
    return record


def review_arc(session, req):
    if req.arc not in {letter for letter, _, _ in ARCS} or not req.reason.strip():
        raise ValueError("Select an actual Reloaded arc A–U and record the GM's progress ruling.")
    record = StrahdArcReview(arc=req.arc, status=req.status, reason=req.reason.strip())
    session.strahd_progress.arc_reviews.append(record)
    return record
