package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp25 email-unique, UPDATED by cp28: the email duplicate check is expressed through the identityKey
 *  (which includes the email). A repeated full identity, email and all, collides with 409. */
@Tag("cp25")
class Cp25Tests extends AcceptanceBase {

	@Test
	void coreEmailIdentityCollisionRejected() throws Exception {
		ObjectNode a = ownerNode();
		a.put("email", uniqueEmail());
		createOwnerOk(a);
		ObjectNode b = a.deepCopy(); // same telephone / email / household -> same identityKey
		b.put("sharesHousehold", true);
		createOwner(b).andExpect(status().isConflict());
	}
}
