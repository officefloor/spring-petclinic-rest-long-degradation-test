package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp10 household-duplicate: Reject creating an owner when another owner has the same lastName and the same address (co... */
@Tag("cp10")
class Cp10Tests extends AcceptanceBase {

	@Test
	void coreRejectsSameLastNameAndAddress() throws Exception {
		ObjectNode a = ownerNode();
		createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("lastName", a.get("lastName").asText()); b.put("address", a.get("address").asText());
		createOwner(b).andExpect(status().isConflict());
	}

	@Test
	void functionalityAllowsDifferentAddress() throws Exception {
		ObjectNode a = ownerNode();
		createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("lastName", a.get("lastName").asText());
		createOwner(b).andExpect(status().is2xxSuccessful());
	}

	@Test
	void functionalityAllowsWithSharesHousehold() throws Exception {
		ObjectNode a = ownerNode();
		createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("lastName", a.get("lastName").asText()); b.put("address", a.get("address").asText());
		b.put("sharesHousehold", true);
		createOwner(b).andExpect(status().is2xxSuccessful());
	}
}
