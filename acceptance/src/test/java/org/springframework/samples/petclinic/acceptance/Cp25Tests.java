package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** email-unique: Reject creating an owner whose lower-cased email is already used by any other owner. Respo... */
@Tag("cp25")
class Cp25Tests extends AcceptanceBase {

	@Test
	void coreRejectsDuplicateEmail() throws Exception {
		ObjectNode a = ownerNode();
		a.put("email", uniqueEmail());
		createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("email", a.get("email").asText());
		createOwner(b).andExpect(status().isConflict());
	}
}
