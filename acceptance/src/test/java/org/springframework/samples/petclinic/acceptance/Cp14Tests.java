package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp14: on update, reject changing telephone to one already used (409). */
@Tag("cp14")
class Cp14Tests extends AcceptanceBase {

	@Test
	void coreRejectsUpdateToExistingTelephone() throws Exception {
		String p1 = uniquePhone();
		ObjectNode a = validOwner();
		a.put("telephone", p1);
		createOwnerOk(a);

		int idB = createOwnerOk(validOwner()); // owner B with its own unique phone
		ObjectNode upd = validOwner();
		upd.put("telephone", p1); // collide with owner A
		updateOwner(idB, upd).andExpect(status().isConflict());
	}

	@Test
	void functionalityAllowsKeepingOwnTelephone() throws Exception {
		ObjectNode b = validOwner();
		String own = b.get("telephone").asText();
		int idB = createOwnerOk(b);
		ObjectNode upd = validOwner();
		upd.put("telephone", own); // same number the owner already has -> not a conflict
		updateOwner(idB, upd).andExpect(status().is2xxSuccessful());
	}
}
