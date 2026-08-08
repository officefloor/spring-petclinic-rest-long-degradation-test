package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

/** code-collision: memberId (now under 'identity') stays unique across distinct
 * owners. */
@Tag("cp41")
class Cp41Tests extends AcceptanceBase {

	@Test
	void coreMemberIdsStayUnique() throws Exception {
		String m1 = fetchOwner(createOwnerOk(knownOwner("Sydney"))).get("identity").get("memberId").asText();
		String m2 = fetchOwner(createOwnerOk(knownOwner("Sydney"))).get("identity").get("memberId").asText();
		assertNotEquals(m1, m2);
	}
}
