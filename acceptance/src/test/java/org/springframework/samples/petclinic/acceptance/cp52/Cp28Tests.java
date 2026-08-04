package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp28 identity-key: UPDATED by cp52 (identity-key-v2) — Redesign the identity key: identityKey = SHA-256 hex over (normalizedTelephone + '|' + lowerEmail + '|' + soundex(lastName)); duplicate detection (409) uses this key, still ignoring owners flagged deleted and still applying the email-domain blocklist first */
@Tag("cp28")
class Cp28Tests extends AcceptanceBase {

	@Test
	void coreUpdatedBehaviour() throws Exception {
		// This rule changed. Redesign the identity key: identityKey = SHA-256 hex over (normalizedTelephone + '|' + lowerEmail + '|' + soundex(lastName)); duplicate detection (409) uses this key, still ignoring owners flagged deleted and still applying the email-domain blocklist first.
		// TODO: assert the UPDATED behaviour of "identity-key" under the new spec.
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(status().is2xxSuccessful());
	}
}
