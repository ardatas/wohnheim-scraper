from wohnheim_finder.categories import classify_residence


def test_classifies_christian_categories():
    assert classify_residence("Roncalli-Kolleg katholische Stiftung") == "catholic_church"
    assert classify_residence("Evangelische Studentenwohnheime München ESWM") == "protestant_church"
    assert classify_residence("Collegium Oecumenicum christliche Studiengemeinschaft") == "ecumenical_christian"


def test_classifies_public_and_commercial():
    assert classify_residence("Studierendenwerk Wohnanlage Studentenstadt") == "public_student_union"
    assert classify_residence("THE FIZZ Munich furnished student apartments") == "commercial_private"

