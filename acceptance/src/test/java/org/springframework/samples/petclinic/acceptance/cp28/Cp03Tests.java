package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp03 telephone-unique, UPDATED by cp28: duplicate detection is now the single identityKey
 *  (telephone|email|householdId). Two owners with the same identity collide with 409. */
@Tag("cp03")
class Cp03Tests extends AcceptanceBase {

	@Test
	void coreIdentityCollisionRejected() throws Exception {
		ObjectNode a = ownerNode();
		createOwnerOk(a);
		ObjectNode b = a.deepCopy(); // same telephone / lastName / address -> same identityKey
		b.put("sharesHousehold", true); // bypass the household block; identity still collides
		createOwner(b).andExpect(status().isConflict());
	}
}
