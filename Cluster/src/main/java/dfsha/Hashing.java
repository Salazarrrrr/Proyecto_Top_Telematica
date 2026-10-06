package dfsha;

import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

final class Hashing {
    private Hashing() {}

    static BigInteger sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            return new BigInteger(1, digest);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 no disponible", error);
        }
    }
}
