<?php
if (!isset($_GET['token'])) {
    die("Ugyldigt token.");
}

$token = $_GET['token'];

try {
    // Tjek token i databasen
    $pdo = new PDO('sqlite:database.sqlite');
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

    $stmt = $pdo->prepare("SELECT * FROM password_resets WHERE token = ? AND expires_at > datetime('now')");
    $stmt->execute([$token]);
    $reset = $stmt->fetch();

    if (!$reset) {
        die("Ugyldigt eller udløbet token.");
    }

    if ($_SERVER['REQUEST_METHOD'] === 'POST') {
        $password = $_POST['password'];
        $passwordConfirm = $_POST['password_confirmation'];

        if ($password !== $passwordConfirm) {
            die("Kodeordene matcher ikke.");
        }

        if (strlen($password) < 8) {
            die("Kodeordet skal være mindst 8 tegn.");
        }

        // Her skal du opdatere brugerens kodeord i din hoveddatabase
        // Eksempel (pseudo-kode):
        // $userPDO = new PDO('mysql:host=...;dbname=...', 'bruger', 'kodeord');
        // $userPDO->prepare("UPDATE users SET password = ? WHERE email = ?")
        //     ->execute([password_hash($password, PASSWORD_DEFAULT), $reset['email']]);

        // Slet token
        $pdo->prepare("DELETE FROM password_resets WHERE token = ?")->execute([$token]);

        echo "Dit kodeord er nulstillet! <a href='https://din-hovedapp.dk/login'>Log ind</a>";
    }
} catch (Exception $e) {
    error_log("Fejl: " . $e->getMessage());
    die("Der opstod en fejl. Prøv igen senere.");
}
