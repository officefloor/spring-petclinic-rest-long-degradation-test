package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** telephone-unique: duplicate detection is now the single identityKey
 * (telephone|email|householdId). Two owners with the same identity collide with 409. */
@Tag("cp03")
class Cp03Tests extends AcceptanceBase {

	@Test
	void coreIdentityCollisionRejected() throws Exception {
		ObjectNode a = ownerNode();
		createOwnerOk(a);
		// A pure full duplicate: identical in every identity-bearing field, so it must collide (409)
		// under every later version of the key. Do NOT tweak b (e.g. sharesHousehold), which would
		// de-sync the householdId and let the keys differ before makes householdId computed.
		createOwner(a.deepCopy()).andExpect(status().isConflict());
	}
}
