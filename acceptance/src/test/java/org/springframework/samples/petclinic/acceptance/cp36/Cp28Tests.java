package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** identity-key: the identityKey now uses the computed householdId. A repeated
 * full identity (same telephone / household) still collides with 409. */
@Tag("cp28")
class Cp28Tests extends AcceptanceBase {

	@Test
	void coreIdentityCollisionWithComputedHousehold() throws Exception {
		ObjectNode a = ownerNode();
		a.put("postcode", "2000");
		createOwnerOk(a);
		ObjectNode b = a.deepCopy(); // same telephone / lastName / postcode -> same householdId + identityKey
		b.put("sharesHousehold", true);
		createOwner(b).andExpect(status().isConflict());
	}
}
