package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** household-duplicate: — addresses are compared after normalization. */
@Tag("cp10")
class Cp10Tests extends AcceptanceBase {

	@Test
	void coreRejectsAddressesThatNormalizeEqual() throws Exception {
		ObjectNode a = ownerNode(); a.put("address", "12 Main St");
		createOwnerOk(a);
		ObjectNode b = ownerNode(); b.put("lastName", a.get("lastName").asText());
		b.put("address", "12  main  street");
		createOwner(b).andExpect(status().isConflict());
	}
}
