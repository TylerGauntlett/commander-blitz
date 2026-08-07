## Overview
- Cards currently do not have images
- Moxfield provides an API that can be used to get these

## Details

### Search endpoint
https://api2.moxfield.com/v2/cards/search/user?q=(({card_name_url_encoded}))+include:extras&page=1

Example: https://api2.moxfield.com/v2/cards/search/user?q=((Aesi,+Tyrant+of+Gyre+Strait))+include:extras&page=1


Response:
{
    "hasMore": false,
    "totalCards": 1,
    "data": [
        {
            "id": "AWala",
            "uniqueCardId": "L4Wvg",
            "scryfall_id": "673c21f8-02b6-4ac4-b2fc-df065b4ac662",
            "set": "dsc",
            "set_name": "Duskmourn: House of Horror Commander",
            "name": "Aesi, Tyrant of Gyre Strait",
            "cn": "210",
            "layout": "normal",
            "cmc": 6.0000,
            "type": "3",
            "type_line": "Legendary Creature \u2014 Serpent",
            "oracle_text": "You may play an additional land on each of your turns.\nLandfall \u2014 Whenever a land you control enters, you may draw a card.",
            "mana_cost": "{4}{G}{U}",
            "power": "5",
            "toughness": "5",
            "colors": [
                "G",
                "U"
            ],
            "color_indicator": [],
            "color_identity": [
                "G",
                "U"
            ],
            "legalities": {
                "standard": "not_legal",
                "future": "not_legal",
                "historic": "not_legal",
                "timeless": "not_legal",
                "gladiator": "not_legal",
                "pioneer": "not_legal",
                "modern": "not_legal",
                "legacy": "legal",
                "pauper": "not_legal",
                "vintage": "legal",
                "penny": "not_legal",
                "commander": "legal",
                "oathbreaker": "legal",
                "standardbrawl": "not_legal",
                "brawl": "not_legal",
                "competitivebrawl": "not_legal",
                "alchemy": "not_legal",
                "paupercommander": "not_legal",
                "duel": "legal",
                "oldschool": "not_legal",
                "premodern": "not_legal",
                "predh": "not_legal",
                "tlr": "not_legal"
            },
            "frame": "2015",
            "frame_effects": [
                "legendary"
            ],
            "reserved": false,
            "digital": false,
            "foil": false,
            "nonfoil": true,
            "etched": false,
            "glossy": false,
            "rarity": "mythic",
            "border_color": "black",
            "colorshifted": false,
            "flavor_text": "\u0022To sail through those waters is to offer oneself as tribute.\u0022\n\u2014Captain Hoyrik",
            "lang": "en",
            "latest": true,
            "has_multiple_editions": true,
            "has_arena_legal": false,
            "prices": {
                "usd": 11.4200,
                "eur": 13.4300,
                "tix": 12.7900,
                "ck": 16.9900,
                "lastUpdatedAtUtc": "2026-08-07T00:20:18.997Z",
                "ck_buy": 10.2500,
                "ck_buy_qty": 65,
                "csi": 9.9900,
                "csi_buy": 4.0000,
                "csi_buy_qty": 20,
                "ct": 13.4600,
                "scg": 11.6900,
                "scg_qty": 1,
                "scg_buy": 0.0000,
                "mp": 10.0000,
                "mp_qty": 69
            },
            "card_faces": [],
            "artist": "Viktor Titov",
            "promo_types": [],
            "cardHoarderUrl": "https://www.cardhoarder.com/cards/131045?affiliate_id=moxfield\u0026ref=card-profile\u0026utm_campaign=affiliate\u0026utm_medium=card\u0026utm_source=moxfield",
            "cardKingdomUrl": "mtg/duskmourn-house-of-horror-commander-decks/aesi-tyrant-of-gyre-strait",
            "cardMarketUrl": "https://www.cardmarket.com/en/Magic/Products?idProduct=788947\u0026referrer=moxfield\u0026utm_campaign=card_prices\u0026utm_medium=text\u0026utm_source=moxfield",
            "tcgPlayerUrl": "https://partner.tcgplayer.com/c/4949650/1830156/21018?subId1=api\u0026u=https%3A%2F%2Fwww.tcgplayer.com%2Fproduct%2F577847%3Fpage%3D1",
            "isArenaLegal": false,
            "released_at": "2024-09-27",
            "edhrec_rank": 846,
            "multiverse_ids": [
                676083
            ],
            "cardmarket_id": 788947,
            "mtgo_id": 131045,
            "tcgplayer_id": 577847,
            "cardkingdom_id": 301801,
            "reprint": true,
            "set_type": "commander",
            "coolStuffIncUrl": "http://www.coolstuffinc.com/p/Magic%3A\u002BThe\u002BGathering/Aesi%2C\u002BTyrant\u002Bof\u002BGyre\u002BStrait",
            "acorn": false,
            "image_seq": 324998367,
            "cardTraderUrl": "https://www.cardtrader.com/cards/300860",
            "cardTraderFoilUrl": "https://www.cardtrader.com/cards/300860",
            "content_warning": false,
            "starcitygames_sku": "SGL-MTG-DSC-210-ENN",
            "starcitygames_url": "https://starcitygames.com/aesi-tyrant-of-gyre-strait-sgl-mtg-dsc-210-enn/",
            "isPauperCommander": false,
            "isCovered": true,
            "allRaritiesMask": 8,
            "manapool_url": "https://manapool.com/card/dsc/210/aesi-tyrant-of-gyre-strait",
            "providerPrices": {
                "journeysend": {
                    "nonFoil": {
                        "retail": 13.0000
                    }
                }
            },
            "isTemporary": false,
            "isToken": false,
            "defaultFinish": "nonFoil"
        }
    ],
    "ownedCards": {}
}


### Image Lookup

https://assets.moxfield.net/cards/card-{card_id}-normal.webp

Example: https://assets.moxfield.net/cards/card-AWala-normal.webp


## Task
- Using query + image endpoints, a simple python class should be possible to get hydrated information for the card
- These images can be stored within the repo
- A python script can be set up to import images for a given card/deck
- Once imported, it should skip pulling the image on subsequent runs as to make it efficent