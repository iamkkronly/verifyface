# Test fixtures — credits

Developer: Kaustav Kanti Ray

These photographs are used **only** as automated-test inputs. They are not part
of the library, are not needed at runtime, and no biometric template derived
from them is stored in the repository.

| File | Person | Source | Author | License |
|------|--------|--------|--------|---------|
| `person_a_1.jpg` | Emmanuel Macron (2014) | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Emmanuel_Macron_(27_ao%C3%BBt_2014).jpg) | Ministère de l'Economie et des Finances français | CC BY-SA 3.0 fr |
| `person_a_2.jpg` | Emmanuel Macron (2025) | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Emmanuel_Macron_2025_(cropped).jpg) | Nebojša Tejić | Public domain |
| `person_b_1.jpg` | Jacinda Ardern (2018) | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:New_Zealand_Prime_Minister_Jacinda_Ardern_in_2018.jpg) | Newzild | CC BY-SA 4.0 |
| `person_b_2.jpg` | Jacinda Ardern (2022) | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Jacinda_Ardern_May_2022.jpg) | Office of the Vice President of the United States | Public domain |
| `impostor_1.jpg` | Barack Obama | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:BarackObamaportrait.jpg) | United States Senate | Public domain |
| `impostor_2.jpg` | Rishi Sunak | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Official_portrait_of_Rishi_Sunak_crop_2.jpg) | Chris McAndrew | CC BY 3.0 |

The pairs `person_a_*` and `person_b_*` are the same person photographed years
apart, in different clothes, places and lighting — exactly the situation the
library promises to handle. `impostor_*` are different people and must be
rejected.
