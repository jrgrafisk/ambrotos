# Lightweight "Glemt kodeord"-løsning til one.com

Denne mappe indeholder en **selvstændig, letvægts PHP-løsning** til håndtering af "glemt kodeord", designet til at køre på **one.com**.

## Filer og deres formål

| Fil                  | Beskrivelse                                                                                     |
|----------------------|-------------------------------------------------------------------------------------------------|
| `request_reset.php`  | Håndterer anmodning om nulstilling af kodeord og sender email med nulstillingslink.             |
| `reset_password.php` | Validerer token og opdaterer brugerens kodeord.                                                 |
| `request_reset.html` | HTML-formular til indtastning af email.                                                        |
| `reset_password.html`| HTML-formular til indtastning af nyt kodeord.                                                   |
| `database.sqlite`    | SQLite-database til opbevaring af nulstillings-tokens (oprettes automatisk).                   |
| `composer.json`      | Afhængigheder (PHPMailer) til at sende emails via SMTP.                                         |

## Opsætning

### 1. Upload filer til one.com
Upload alle filer i denne mappe til en undermappe på dit one.com-webhotel, f.eks.:
```
/forgotten-pass/
```

### 2. Installer afhængigheder
Kør følgende kommando i mappen (hvis du har adgang til SSH på one.com):
```bash
composer install
```
Hvis ikke, upload `vendor/`-mappen manuelt efter at have kørt `composer install` lokalt.

### 3. Konfigurer SMTP (one.com)
Rediger `request_reset.php` og opdater SMTP-indstillingerne:
```php
$mail->Host = 'send.one.com';
$mail->Username = 'noreply@jrgrafisk.dk';
$mail->Password = 'dit-email-kodeord';
```

### 4. Konfigurer omdirigering fra hovedapp
I din hovedapplikation (f.eks. på Render), omdiriger brugeren til:
```
https://jrgrafisk.dk/forgotten-pass/request_reset.html
```

### 5. Test løsningen
1. Gå til `https://jrgrafisk.dk/forgotten-pass/request_reset.html`.
2. Indtast en email og send anmodningen.
3. Tjek din indbakke for nulstillingslinket.
4. Klik på linket og nulstil kodeordet.

## Sikkerhed
- **Brug HTTPS** for alle links.
- **Slet tokens** efter brug.
- **Valider input** på både client- og server-side.

## Database
SQLite-filen (`database.sqlite`) oprettes automatisk, når den første anmodning modtages.

## Eksempel på integration med hovedapp
I din hovedapplikation, link til:
```html
<a href="https://jrgrafisk.dk/forgotten-pass/request_reset.html">Glemt kodeord?</a>
```

## Fejlfinding
- Tjek `error.log` på one.com, hvis emails ikke sendes.
- Sørg for, at `database.sqlite` har skriverettigheder (CHMOD 664).

## Licens
MIT