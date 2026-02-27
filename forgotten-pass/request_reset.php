<?php
require 'vendor/autoload.php';

use PHPMailer\PHPMailer\PHPMailer;
use PHPMailer\PHPMailer\Exception;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $email = filter_input(INPUT_POST, 'email', FILTER_SANITIZE_EMAIL);
    
    if (!$email) {
        die("Ugyldig email.");
    }

    // Opret token (gyldigt i 1 time)
    $token = bin2hex(random_bytes(32));
    $expires = date('Y-m-d H:i:s', strtotime('+1 hour'));

    try {
        // Opret SQLite-forbindelse
        $pdo = new PDO('sqlite:database.sqlite');
        $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

        // Opret tabellen hvis den ikke findes
        $pdo->exec(""
            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                token TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        "");

        // Gem token i databasen
        $stmt = $pdo->prepare("INSERT INTO password_resets (email, token, expires_at) VALUES (?, ?, ?)");
        $stmt->execute([$email, $token, $expires]);

        // Send email med PHPMailer
        $mail = new PHPMailer(true);
        $mail->isSMTP();
        $mail->Host = 'send.one.com';
        $mail->Port = 587;
        $mail->SMTPAuth = true;
        $mail->Username = 'noreply@jrgrafisk.dk';
        $mail->Password = 'dit-email-kodeord';
        $mail->setFrom('noreply@jrgrafisk.dk', 'Ambrotos');
        $mail->addAddress($email);
        $mail->isHTML(false);
        $mail->Subject = 'Nulstil dit kodeord';
        $mail->Body = "Hej,\n\nDu har anmodet om at nulstille dit kodeord. Klik på linket nedenfor:\n\nhttps://jrgrafisk.dk/forgotten-pass/reset_password.php?token=$token\n\nLinket udløber om 1 time.\n\nHilsen,\nAmbrotos";

        $mail->send();

        echo "Nulstillingslink er sendt til din email!";
    } catch (Exception $e) {
        error_log("Fejl: " . $e->getMessage());
        die("Der opstod en fejl. Prøv igen senere.");
    }
}
