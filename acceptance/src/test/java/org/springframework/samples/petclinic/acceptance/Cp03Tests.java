package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp03: normalise telephone (strip spaces, dashes, parentheses) before saving. */
@Tag("cp03")
class Cp03Tests extends AcceptanceBase {

	@Test
	void coreStripsFormattingBeforeSave() throws Exception {
		ObjectNode o = validOwner();
		o.put("telephone", "(613) 555-0123");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.telephone").value("6135550123"));
	}

	@Test
	void functionalityNormalisesOnUpdate() throws Exception {
		int id = createOwnerOk(validOwner());
		ObjectNode upd = validOwner();
		upd.put("telephone", " 613 555 0124 ");
		updateOwner(id, upd).andExpect(status().is2xxSuccessful());
		getOwner(id).andExpect(jsonPath("$.telephone").value("6135550124"));
	}
}
